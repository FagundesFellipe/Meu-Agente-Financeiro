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
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from financial_agent.agent.state_graph import PaymentMethod, RecurringExpenseDetails
from financial_agent.agent.tools.get_category import normalize
from shared.db import DictConnection, user_connection
from shared.repositories._locks import ADVISORY_TRANSACTION_LOCK, advisory_lock_key

_LOCK_NAMESPACE = "recurring_expense"

_SELECT_ACTIVE = """
    SELECT r.id, r.description, r.amount, r.payment_method, r.recurrence_day,
           r.starts_at, r.ends_at, r.category_id, c.name AS category_name
    FROM recurring_expense r
    JOIN category c ON c.id = r.category_id
    WHERE r.user_id = %(user_id)s
      AND r.is_active IS TRUE
    ORDER BY r.created_at
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
