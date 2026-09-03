"""Persistência e leitura da tabela ``recurring_expense`` (gastos fixos).

Regras que este módulo garante:
    - Isolamento por usuário: toda query passa por ``user_connection`` e repete
      o filtro ``user_id`` explicitamente (RLS não se aplica ao owner da tabela).
    - Sem duplicata: uma regra ativa com a mesma descrição normalizada bloqueia
      a inserção de outra. Valor e dia não entram na comparação — uma "Netflix"
      já cadastrada continua sendo a Netflix mesmo que o preço mude.
    - Idempotência: a mesma mensagem reprocessada pelo worker não cria linhas
      novas. ``recurring_expense`` não tem ``source_message_id``, então o efeito
      vem da combinação do advisory lock com a checagem por descrição — o
      resultado observável é o mesmo.
    - Dinheiro em ``Decimal``/NUMERIC — nunca float binário.

O módulo também materializa as regras em lançamentos reais
(``materialize_due_recurring_expenses``). A materialização é deliberadamente
independente do grafo — recebe ``user_id`` e ``today`` — para que um processo
agendado futuro possa chamá-la sem qualquer alteração.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from financial_agent.agent.state_graph import PaymentMethod, RecurringExpenseDetails
from financial_agent.agent.tools.get_category import normalize
from financial_agent.agent.tools.recurrence import (
    MAX_RETROACTIVE_PERIODS,
    PendingPeriods,
    effective_date,
    pending_periods,
)
from shared.db import DictConnection, user_connection
from shared.repositories._locks import ADVISORY_TRANSACTION_LOCK, advisory_lock_key
from shared.repositories.expenses import (
    ExpenseRecord,
    insert_creation_audit,
    to_expense_record,
)

logger = structlog.get_logger()

_LOCK_NAMESPACE = "recurring_expense"
_CATCHUP_LOCK_NAMESPACE = "recurring_catchup"

# Meio-dia replica a convenção de ``resolve_occurred_at`` para datas passadas:
# gravar 00:00 desloca o lançamento para o dia anterior em fusos a oeste de UTC.
_CHARGE_TIME = time(12, 0)

_SELECT_ACTIVE = """
    SELECT r.id, r.description, r.amount, r.payment_method, r.recurrence_day,
           r.starts_at, r.ends_at, r.category_id, c.name AS category_name
    FROM recurring_expense r
    JOIN category c ON c.id = r.category_id
    WHERE r.user_id = %(user_id)s
      AND r.is_active IS TRUE
    ORDER BY r.created_at
"""

_SELECT_ACTIVE_WITH_GENERATED_PERIODS = """
    SELECT r.id, r.description, r.amount, r.payment_method, r.recurrence_day,
           r.starts_at, r.ends_at, r.category_id, c.name AS category_name,
           COALESCE(
               ARRAY_AGG(e.recurrence_period)
                   FILTER (WHERE e.recurrence_period IS NOT NULL),
               ARRAY[]::DATE[]
           ) AS generated_periods
    FROM recurring_expense r
    JOIN category c ON c.id = r.category_id
    LEFT JOIN expense e
           ON e.recurring_expense_id = r.id
          AND e.user_id = %(user_id)s
    WHERE r.user_id = %(user_id)s
      AND r.is_active IS TRUE
    GROUP BY r.id, c.name
    ORDER BY r.created_at
"""

_INSERT_MATERIALIZED_EXPENSE = """
    INSERT INTO expense (
        user_id, category_id, recurring_expense_id, recurrence_period,
        amount, description, original_description, payment_method, occurred_at
    ) VALUES (
        %(user_id)s, %(category_id)s, %(recurring_expense_id)s, %(recurrence_period)s,
        %(amount)s, %(description)s, %(original_description)s, %(payment_method)s,
        %(occurred_at)s
    )
    ON CONFLICT (recurring_expense_id, recurrence_period)
    WHERE recurring_expense_id IS NOT NULL
    DO NOTHING
    RETURNING id, amount, description, original_description, payment_method,
              occurred_at, category_id, installment_number, total_installments,
              recurrence_period
"""

_INSERT_RECURRING_EXPENSE = """
    INSERT INTO recurring_expense (
        user_id, category_id, description, amount,
        payment_method, recurrence_day, starts_at
    )
    VALUES (
        %(user_id)s, %(category_id)s, %(description)s, %(amount)s,
        %(payment_method)s, %(recurrence_day)s, %(starts_at)s
    )
    RETURNING id, description, amount, payment_method, recurrence_day,
              starts_at, ends_at, category_id
"""


@dataclass(frozen=True, slots=True)
class RecurringExpenseRecord:
    """Regra de gasto fixo como está gravada no banco."""

    id: UUID
    description: str
    amount: Decimal
    payment_method: PaymentMethod
    recurrence_day: int
    starts_at: date
    ends_at: date | None
    category_id: UUID
    category_name: str


@dataclass(frozen=True, slots=True)
class InsertRecurringResult:
    """O que aconteceu com cada regra enviada para inserção.

    ``duplicates`` traz a regra **já existente** que bloqueou a inserção, não a
    que foi recusada — é ela que o nó precisa para dizer ao usuário com que
    valor e em que dia o gasto fixo já está cadastrado.
    """

    inserted: list[RecurringExpenseRecord]
    duplicates: list[RecurringExpenseRecord]


def _to_record(row: dict, category_name: str) -> RecurringExpenseRecord:
    return RecurringExpenseRecord(
        id=row["id"],
        description=row["description"],
        amount=row["amount"],
        payment_method=row["payment_method"],
        recurrence_day=row["recurrence_day"],
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
        category_id=row["category_id"],
        category_name=category_name,
    )


async def _fetch_active(
    conn: DictConnection, user_id: str
) -> list[RecurringExpenseRecord]:
    cur = await conn.execute(_SELECT_ACTIVE, {"user_id": user_id})
    rows = await cur.fetchall()
    return [_to_record(row, row["category_name"]) for row in rows]


def _index_by_normalized_description(
    records: list[RecurringExpenseRecord],
) -> dict[str, RecurringExpenseRecord]:
    """Indexa as regras ativas pela descrição normalizada, mantendo a mais antiga."""
    index: dict[str, RecurringExpenseRecord] = {}
    for record in records:
        index.setdefault(normalize(record.description), record)
    return index


async def list_active_recurring_expenses(
    user_id: str | UUID,
) -> list[RecurringExpenseRecord]:
    """Retorna as regras de gasto fixo ativas do usuário, da mais antiga à mais nova."""
    async with user_connection(str(user_id)) as conn:
        return await _fetch_active(conn, str(user_id))


async def find_active_by_normalized_description(
    user_id: str | UUID, description: str
) -> RecurringExpenseRecord | None:
    """Procura uma regra ativa cuja descrição normalizada seja igual à informada.

    A normalização é feita em Python (``normalize``), então a comparação não
    pode acontecer no ``WHERE`` sem uma coluna gerada no banco.
    """
    active = await list_active_recurring_expenses(user_id)
    return _index_by_normalized_description(active).get(normalize(description))


async def insert_recurring_expenses(
    user_id: str | UUID,
    recurring_expenses: list[RecurringExpenseDetails],
    source_message_id: str | UUID | None = None,
) -> InsertRecurringResult:
    """Grava as regras de gasto fixo de uma mensagem, sem criar duplicatas.

    A leitura das regras ativas e as inserções acontecem na mesma transação,
    atrás de um advisory lock por mensagem de origem: duas execuções
    concorrentes do mesmo usuário não conseguem inserir a mesma regra duas
    vezes, e reprocessar a mensagem devolve a regra existente como duplicata.

    Args:
        user_id: Dono das regras.
        recurring_expenses: Regras já validadas em Python.
        source_message_id: Mensagem de origem (``message_queue.id``).

    Returns:
        As regras criadas e, para cada regra recusada, a regra já existente que
        a bloqueou.
    """
    if not recurring_expenses:
        return InsertRecurringResult(inserted=[], duplicates=[])

    user_id_str = str(user_id)
    lock_scope = str(source_message_id) if source_message_id else user_id_str

    async with user_connection(user_id_str) as conn:
        await conn.execute(
            ADVISORY_TRANSACTION_LOCK,
            (advisory_lock_key(_LOCK_NAMESPACE, lock_scope),),
        )

        existing_by_description = _index_by_normalized_description(
            await _fetch_active(conn, user_id_str)
        )

        inserted: list[RecurringExpenseRecord] = []
        duplicates: list[RecurringExpenseRecord] = []

        for recurring_expense in recurring_expenses:
            already_registered = existing_by_description.get(
                normalize(recurring_expense.description)
            )
            if already_registered is not None:
                duplicates.append(already_registered)
                continue

            record = await _insert_one(conn, user_id_str, recurring_expense)
            existing_by_description[normalize(record.description)] = record
            inserted.append(record)

    return InsertRecurringResult(inserted=inserted, duplicates=duplicates)


async def _insert_one(
    conn: DictConnection, user_id: str, recurring_expense: RecurringExpenseDetails
) -> RecurringExpenseRecord:
    cur = await conn.execute(
        _INSERT_RECURRING_EXPENSE,
        {
            "user_id": user_id,
            "category_id": str(recurring_expense.category_id),
            "description": recurring_expense.description,
            "amount": recurring_expense.amount,
            "payment_method": recurring_expense.payment_method,
            "recurrence_day": recurring_expense.recurrence_day,
            "starts_at": recurring_expense.starts_at,
        },
    )
    row = await cur.fetchone()
    if row is None:  # pragma: no cover - RETURNING sempre devolve linha
        raise RuntimeError("INSERT em recurring_expense não retornou linha")

    return _to_record(row, recurring_expense.category_name)


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    """O que uma execução de catch-up produziu, para log e para os testes."""

    generated: list[ExpenseRecord]
    rules_processed: int
    truncated_rules: list[UUID]


@dataclass(frozen=True, slots=True)
class _ActiveRule:
    """Regra ativa junto das competências que ela já materializou."""

    rule: RecurringExpenseRecord
    generated_periods: frozenset[date]


async def materialize_due_recurring_expenses(
    user_id: str | UUID,
    today: date,
    user_timezone: str,
) -> MaterializationResult:
    """Cria os lançamentos que as regras ativas do usuário já deveriam ter gerado.

    A operação é idempotente por construção: a chave
    ``(recurring_expense_id, recurrence_period)`` é única no banco, e o
    ``ON CONFLICT DO NOTHING`` absorve a corrida que o advisory lock não pegar.
    Executá-la N vezes no mesmo dia produz o mesmo resultado de uma única
    execução.

    Não depende do grafo: um processo agendado futuro pode chamá-la como está.

    Args:
        user_id: Dono das regras e dos lançamentos.
        today: Data de referência no fuso do usuário. Injetada, nunca lida do
            relógio, para manter o comportamento determinístico.
        user_timezone: Fuso IANA do usuário, usado para posicionar
            ``occurred_at``.

    Returns:
        Os lançamentos criados, quantas regras foram avaliadas e quais tiveram
        períodos além do limite retroativo.
    """
    user_id_str = str(user_id)
    zone = ZoneInfo(user_timezone)

    generated: list[ExpenseRecord] = []
    truncated_rules: list[UUID] = []

    async with user_connection(user_id_str) as conn:
        # Serializa o catch-up concorrente do mesmo usuário: sem isso, dois
        # workers leriam a mesma lista de competências pendentes.
        await conn.execute(
            ADVISORY_TRANSACTION_LOCK,
            (advisory_lock_key(_CATCHUP_LOCK_NAMESPACE, user_id_str),),
        )

        active_rules = await _fetch_active_with_generated_periods(conn, user_id_str)

        for active in active_rules:
            due = _due_periods(active, today, user_id_str)
            if due.remaining:
                truncated_rules.append(active.rule.id)

            for period in due.due:
                record = await _materialize_period(
                    conn, user_id_str, active.rule, period, zone
                )
                if record is not None:
                    generated.append(record)

    return MaterializationResult(
        generated=generated,
        rules_processed=len(active_rules),
        truncated_rules=truncated_rules,
    )


def _due_periods(active: _ActiveRule, today: date, user_id: str) -> PendingPeriods:
    """Períodos a gerar agora, registrando em log o que ficou para a próxima."""
    due = pending_periods(
        recurrence_day=active.rule.recurrence_day,
        starts_at=active.rule.starts_at,
        ends_at=active.rule.ends_at,
        already_generated=active.generated_periods,
        today=today,
        limit=MAX_RETROACTIVE_PERIODS,
    )

    if due.remaining:
        logger.info(
            "recurring_catchup_truncated",
            user_id=user_id,
            recurring_expense_id=str(active.rule.id),
            remaining_periods=due.remaining,
        )

    return due


async def _fetch_active_with_generated_periods(
    conn: DictConnection, user_id: str
) -> list[_ActiveRule]:
    cur = await conn.execute(
        _SELECT_ACTIVE_WITH_GENERATED_PERIODS, {"user_id": user_id}
    )
    rows = await cur.fetchall()
    return [
        _ActiveRule(
            rule=_to_record(row, row["category_name"]),
            generated_periods=frozenset(row["generated_periods"]),
        )
        for row in rows
    ]


async def _materialize_period(
    conn: DictConnection,
    user_id: str,
    rule: RecurringExpenseRecord,
    period: date,
    zone: ZoneInfo,
) -> ExpenseRecord | None:
    """Insere o lançamento de um período, ou ``None`` se outra execução ganhou."""
    occurred_at = datetime.combine(
        effective_date(rule.recurrence_day, period), _CHARGE_TIME, tzinfo=zone
    )

    cur = await conn.execute(
        _INSERT_MATERIALIZED_EXPENSE,
        {
            "user_id": user_id,
            "category_id": str(rule.category_id),
            "recurring_expense_id": str(rule.id),
            "recurrence_period": period,
            "amount": rule.amount,
            "description": rule.description,
            "original_description": rule.description,
            "payment_method": rule.payment_method,
            "occurred_at": occurred_at,
        },
    )
    row = await cur.fetchone()
    if row is None:
        return None

    record = to_expense_record(row, rule.category_name)
    await insert_creation_audit(
        conn,
        user_id=user_id,
        expense_id=record.id,
        after_data={
            "amount": str(record.amount),
            "description": record.description,
            "original_description": record.original_description,
            "payment_method": record.payment_method,
            "occurred_at": record.occurred_at.isoformat(),
            "category_id": str(record.category_id),
            "category_name": record.category_name,
            "recurring_expense_id": str(rule.id),
            "recurrence_period": period.isoformat(),
        },
        source_message_id=None,
    )
    return record
