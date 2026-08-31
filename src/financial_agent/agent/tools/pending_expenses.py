"""Operações determinísticas sobre rascunhos de gastos pendentes."""

from datetime import datetime, timedelta
from uuid import uuid4

from financial_agent.agent.state_graph import PendingExpense

PENDING_EXPENSE_TTL = timedelta(hours=24)


def enforce_missing_field_dependencies(pending: PendingExpense) -> PendingExpense:
    """Corrige `missing_fields` para refletir o que pode ser considerado confirmado.

    O LLM às vezes marca só `description` como faltando, mas deixa `category_hint`
    em branco sem marcar `category` como faltando também. Categoria de um item
    desconhecido nunca é segura — ela depende do próprio item. Sem essa correção,
    o guard determinístico (``_accept_if_confirmed_fields_untouched`` em
    resolve_pending_expenses_agent) trata esse branco como "confirmado: sem
    categoria" e trava a pendência para sempre, mesmo depois da descrição ser
    respondida.
    """
    if (
        "description" in pending.missing_fields
        and "category" not in pending.missing_fields
    ):
        return pending.model_copy(
            update={
                "missing_fields": [*pending.missing_fields, "category"],
                "category_hint": None,
            }
        )
    return pending


def assign_pending_metadata(
    pending_expenses: list[PendingExpense], now: datetime
) -> list[PendingExpense]:
    """Cria identificadores estáveis para os rascunhos desta extração."""
    return [
        enforce_missing_field_dependencies(pending).model_copy(
            update={
                "id": uuid4().hex,
                "created_at": now,
            }
        )
        for pending in pending_expenses
    ]


def keep_pending_metadata(pending: PendingExpense, now: datetime) -> PendingExpense:
    """Garante metadados para rascunhos produzidos fora da extração principal."""
    return enforce_missing_field_dependencies(pending).model_copy(
        update={
            "id": pending.id or uuid4().hex,
            "created_at": pending.created_at or now,
        }
    )


def split_expired_pending_expenses(
    pending_expenses: list[PendingExpense], now: datetime
) -> tuple[list[PendingExpense], list[PendingExpense]]:
    """Separa pendências ativas das que ultrapassaram a janela de 24 horas."""
    expiration_cutoff = now - PENDING_EXPENSE_TTL
    active: list[PendingExpense] = []
    expired: list[PendingExpense] = []

    for pending in pending_expenses:
        if pending.created_at is not None and pending.created_at <= expiration_cutoff:
            expired.append(pending)
        else:
            active.append(pending)

    return active, expired


def format_pending_questions(pending_expenses: list[PendingExpense]) -> str:
    """Agrupa as perguntas sem transformar rascunhos em gastos confirmados."""
    return "\n".join(pending.clarification_message for pending in pending_expenses)


def format_expired_pending_message() -> str:
    """Explica como retomar uma pendência que não existe mais no checkpoint."""
    return (
        "Essa pendência expirou após 24 horas. Envie novamente o gasto completo, "
        "com descrição e valor, para eu registrar com segurança."
    )
