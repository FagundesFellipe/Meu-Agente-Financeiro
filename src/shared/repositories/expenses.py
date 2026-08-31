"""Persistência e leitura da tabela ``expense``.

Regras que este módulo garante:
    - Isolamento por usuário: toda query passa por ``user_connection``.
    - Idempotência: reprocessar a mesma ``source_message_id`` não duplica gastos
      (RF de idempotência do PRD §16).
    - Auditoria: cada inserção gera uma linha ``created`` em ``expense_audit_log``.
    - Dinheiro em ``Decimal``/NUMERIC — nunca float binário.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from psycopg.types.json import Jsonb

from financial_agent.agent.state_graph import ExpenseDetails, PaymentMethod
from shared.db import DictConnection, user_connection
from shared.repositories._locks import ADVISORY_TRANSACTION_LOCK, advisory_lock_key

_SELECT_BY_SOURCE_MESSAGE = """
    SELECT e.id, e.amount, e.description, e.original_description,
           e.payment_method, e.occurred_at, e.category_id, c.name AS category_name,
           e.installment_number, e.total_installments
    FROM expense e
    JOIN category c ON c.id = e.category_id
    WHERE e.user_id = %(user_id)s
      AND e.source_message_id = %(source_message_id)s
    ORDER BY e.created_at
"""

_INSERT_EXPENSE = """
    INSERT INTO expense (
        user_id, category_id, source_message_id, amount,
        description, original_description, payment_method,
        occurred_at, confidence, installment_number, total_installments
    )
    VALUES (
        %(user_id)s, %(category_id)s, %(source_message_id)s, %(amount)s,
        %(description)s, %(original_description)s, %(payment_method)s,
        %(occurred_at)s, %(confidence)s, %(installment_number)s, %(total_installments)s
    )
    RETURNING id, amount, description, original_description,
              payment_method, occurred_at, category_id,
              installment_number, total_installments
"""

_INSERT_AUDIT = """
    INSERT INTO expense_audit_log
        (expense_id, user_id, action, before_data, after_data, source_message_id)
    VALUES
        (%(expense_id)s, %(user_id)s, 'created', NULL, %(after_data)s,
         %(source_message_id)s)
"""

_SELECT_LAST = """
    SELECT e.id, e.amount, e.description, e.original_description,
           e.payment_method, e.occurred_at, e.category_id, c.name AS category_name,
           e.installment_number, e.total_installments
    FROM expense e
    JOIN category c ON c.id = e.category_id
    WHERE e.user_id = %(user_id)s
    ORDER BY e.created_at DESC
    LIMIT 1
"""


@dataclass(frozen=True, slots=True)
class ExpenseRecord:
    """Gasto como está gravado no banco."""

    id: UUID
    amount: Decimal
    description: str
    original_description: str | None
    payment_method: PaymentMethod
    occurred_at: datetime
    category_id: UUID
    category_name: str
    installment_number: int | None = None
    total_installments: int | None = None


def _to_record(row: dict, category_name: str) -> ExpenseRecord:
    return ExpenseRecord(
        id=row["id"],
        amount=row["amount"],
        description=row["description"],
        original_description=row["original_description"],
        payment_method=row["payment_method"],
        occurred_at=row["occurred_at"],
        category_id=row["category_id"],
        category_name=category_name,
        installment_number=row.get("installment_number"),
        total_installments=row.get("total_installments"),
    )


async def _fetch_by_source_message(
    conn: DictConnection, user_id: str, source_message_id: str
) -> list[ExpenseRecord]:
    cur = await conn.execute(
        _SELECT_BY_SOURCE_MESSAGE,
        {"user_id": user_id, "source_message_id": source_message_id},
    )
    rows = await cur.fetchall()
    return [_to_record(row, row["category_name"]) for row in rows]


async def insert_expenses(
    user_id: str | UUID,
    expenses: list[ExpenseDetails],
    source_message_id: str | UUID | None = None,
) -> list[ExpenseRecord]:
    """Grava os gastos de uma mensagem, de forma idempotente e auditada.

    Se ``source_message_id`` já produziu gastos, nenhuma linha nova é criada e
    os gastos existentes são retornados — é isso que torna seguro o retry do
    worker e o reenvio do webhook.

    Args:
        user_id: Dono dos gastos.
        expenses: Gastos já validados em Python.
        source_message_id: Mensagem de origem (``message_queue.id``).

    Returns:
        Os gastos gravados, na ordem de inserção.
    """
    if not expenses:
        return []

    user_id_str = str(user_id)
    source_id_str = str(source_message_id) if source_message_id else None

    async with user_connection(user_id_str) as conn:
        if source_id_str is not None:
            # Serializa retries concorrentes da mesma mensagem antes de checar.
            await conn.execute(
                ADVISORY_TRANSACTION_LOCK,
                (advisory_lock_key("expense", source_id_str),),
            )

            existing = await _fetch_by_source_message(conn, user_id_str, source_id_str)
            if existing:
                return existing

        records: list[ExpenseRecord] = []
        for expense in expenses:
            cur = await conn.execute(
                _INSERT_EXPENSE,
                {
                    "user_id": user_id_str,
                    "category_id": str(expense.category_id),
                    "source_message_id": source_id_str,
                    "amount": expense.amount,
                    "description": expense.description,
                    "original_description": expense.original_description,
                    "payment_method": expense.payment_method,
                    "occurred_at": expense.occurred_at,
                    "confidence": expense.confidence,
                    "installment_number": expense.installment_number,
                    "total_installments": expense.total_installments,
                },
            )
            row = await cur.fetchone()
            if row is None:  # pragma: no cover - RETURNING sempre devolve linha
                raise RuntimeError("INSERT em expense não retornou linha")

            record = _to_record(row, expense.category_name)
            records.append(record)

            await conn.execute(
                _INSERT_AUDIT,
                {
                    "expense_id": str(record.id),
                    "user_id": user_id_str,
                    "after_data": Jsonb(
                        {
                            "amount": str(record.amount),
                            "description": record.description,
                            "original_description": record.original_description,
                            "payment_method": record.payment_method,
                            "occurred_at": record.occurred_at.isoformat(),
                            "category_id": str(record.category_id),
                            "category_name": record.category_name,
                            "confidence": expense.confidence,
                            "installment_number": expense.installment_number,
                            "total_installments": expense.total_installments,
                        }
                    ),
                    "source_message_id": source_id_str,
                },
            )

    return records


async def get_last_expense(user_id: str | UUID) -> ExpenseRecord | None:
    """Retorna o gasto mais recente do usuário.

    Base para o fluxo de correção (chat só corrige o gasto mais recente,
    conforme regra de produto do PRD). Ainda não é usado pelo agente.
    """
    async with user_connection(str(user_id)) as conn:
        cur = await conn.execute(_SELECT_LAST, {"user_id": str(user_id)})
        row = await cur.fetchone()

    return _to_record(row, row["category_name"]) if row else None
