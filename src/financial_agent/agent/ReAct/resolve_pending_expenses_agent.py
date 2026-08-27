"""Nó que completa ou cancela rascunhos de gastos já pendentes."""

import re
from typing import Any, Literal, cast

import structlog
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from financial_agent.agent.ReAct.add_new_expenses_agent import (
    format_confirmation,
    resolve_extracted_expenses,
)
from financial_agent.agent.state_graph import (
    ExpenseDetails,
    ExtractedExpense,
    GraphState,
    PendingExpense,
    PendingExpenseResolutionRoute,
)
from financial_agent.agent.tools import calendar as tools_calendar
from financial_agent.agent.tools.pending_expenses import (
    format_expired_pending_message,
    format_pending_questions,
)
from shared.agent_builder import build_agent_for_version
from shared.prompt_loader import get_active_version
from shared.repositories.categories import (
    CategoryRecord,
    format_categories_for_prompt,
    list_available_categories,
)
from shared.repositories.expenses import ExpenseRecord, insert_expenses

logger = structlog.get_logger()

_PENDING_RESOLUTION_PROMPT_NAME = "RESOLVE_PENDING_EXPENSE"
_CANCELLED_MESSAGE = "Certo, cancelei essa pendência. Nenhum gasto foi registrado."
_AMBIGUOUS_PENDING_MESSAGE = (
    "Tenho mais de uma pendência. Diga qual gasto você quer completar ou cancelar."
)
_NO_PENDING_MESSAGE = "Não encontrei uma pendência ativa. Envie o gasto completo."
_CANCELLATION_PATTERN = re.compile(r"\b(cancelar|cancele|desisto|desistir)\b", re.I)


class PendingExpenseResolutionResult(BaseModel):
    """Decisão do modelo para um único rascunho e a resposta mais recente."""

    status: Literal["completed", "cancelled", "new_expense", "not_applicable"]
    expense: ExtractedExpense | None = None
    clarification_message: str | None = None


def build_pending_expense_resolution_agent() -> Any:
    """Constrói o agente dedicado, a partir do prompt cadastrado manualmente."""

    version = get_active_version(_PENDING_RESOLUTION_PROMPT_NAME)
    return build_agent_for_version(
        prompt_name=_PENDING_RESOLUTION_PROMPT_NAME,
        version=version,
        response_format=ToolStrategy(PendingExpenseResolutionResult),
        agent_name="resolve_pending_expense_agent",
    )


def _last_user_message(state: GraphState) -> Any:
    """Obtém só a nova resposta, sem reencaminhar o histórico ao resolvedor."""
    return state["messages"][-1]


def _message_text(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", ""))


def build_pending_resolution_context(
    pending: PendingExpense,
    now: Any,
    categories: list[CategoryRecord],
) -> SystemMessage:
    """Monta o único contexto permitido para uma tentativa de resolução."""
    return SystemMessage(
        content=(
            "# CONTEXTO_DE_PENDENCIA\n"
            f"DATA_HORA_ATUAL: {now.isoformat()}\n"
            f"RASCUNHO_PENDENTE: {pending.model_dump_json()}\n"
            "CATEGORIAS_DISPONIVEIS:\n"
            f"{format_categories_for_prompt(categories)}"
        )
    )


async def _resolve_one_pending_expense(
    pending: PendingExpense,
    last_message: Any,
    now: Any,
    categories: list[CategoryRecord],
) -> PendingExpenseResolutionResult:
    """Pede uma decisão para um único rascunho, isolado das demais conversas."""
    try:
        agent = build_pending_expense_resolution_agent()
        result = await agent.ainvoke(
            {
                "messages": [
                    build_pending_resolution_context(pending, now, categories),
                    last_message,
                ]
            }
        )
        return cast(PendingExpenseResolutionResult, result["structured_response"])
    except Exception:
        logger.exception("pending_expense_resolution_failed", pending_id=pending.id)
        return PendingExpenseResolutionResult(status="not_applicable")


def _is_unambiguous_cancellation(
    state: GraphState, pending_expenses: list[PendingExpense]
) -> bool:
    return len(pending_expenses) == 1 and bool(
        _CANCELLATION_PATTERN.search(_message_text(_last_user_message(state)))
    )


def _response_for_unmatched_pending(pending_expenses: list[PendingExpense]) -> str:
    if len(pending_expenses) > 1:
        return _AMBIGUOUS_PENDING_MESSAGE
    return format_pending_questions(pending_expenses)


def _resolution_state(
    *,
    pending: list[PendingExpense],
    needs_clarification: bool,
    route: PendingExpenseResolutionRoute = "finalize_response",
    clarification_message: str | None = None,
    response_text: str | None = None,
    expense_details: list[ExpenseDetails] | None = None,
) -> dict:
    """Delta de estado devolvido ao grafo por este nó — o contrato num lugar só.

    Todo retorno de :func:`resolve_pending_expenses` passa por aqui, então as
    chaves e seus defaults ficam definidos uma vez. ``expired_pending_expenses``
    é sempre zerado: pendências expiradas já foram tratadas antes deste nó.
    ``response_text`` só entra no dicionário quando informado — o ramo que
    redireciona para ``add_new_expenses_agent`` deixa a resposta para o nó
    seguinte montar.
    """
    delta: dict[str, Any] = {
        "pending_expense_resolution_route": route,
        "pending_expenses": pending,
        "expired_pending_expenses": [],
        "needs_clarification": needs_clarification,
        "clarification_message": clarification_message,
        "expense_details": expense_details or [],
    }
    if response_text is not None:
        delta["response_text"] = response_text
    return delta


def _finalize_cleared(response_text: str) -> dict:
    """Encerra o fluxo sem nenhuma pendência restante."""
    return _resolution_state(
        pending=[], needs_clarification=False, response_text=response_text
    )


def _keep_all_pending(pending: list[PendingExpense], question: str) -> dict:
    """Mantém as pendências como estão e repete a mesma pergunta ao usuário."""
    return _resolution_state(
        pending=pending,
        needs_clarification=True,
        clarification_message=question,
        response_text=question,
    )


def _finalize_one_resolved(
    remaining_pending: list[PendingExpense],
    lead_text: str,
    expense_details: list[ExpenseDetails] | None = None,
) -> dict:
    """Fecha depois de resolver exatamente um rascunho, anexando a próxima pergunta."""
    return _resolution_state(
        pending=remaining_pending,
        needs_clarification=bool(remaining_pending),
        clarification_message=format_pending_questions(remaining_pending) or None,
        response_text=_response_with_remaining_pending(lead_text, remaining_pending),
        expense_details=expense_details,
    )


def _response_with_remaining_pending(
    response_text: str, remaining_pending: list[PendingExpense]
) -> str:
    """Anexa a próxima pergunta quando uma operação resolve só um rascunho."""
    pending_questions = format_pending_questions(remaining_pending)
    return (
        f"{response_text}\n\n{pending_questions}"
        if pending_questions
        else response_text
    )


def _merge_resolved_expense(
    pending: PendingExpense, proposed: ExtractedExpense
) -> ExtractedExpense | None:
    """Aceita somente uma proposta que não altere dados já confirmados."""
    payload = proposed.model_dump()
    protected_fields = {
        "description": pending.description,
        "amount_raw": pending.amount_raw,
        "installments": pending.installments,
        "date_hint": pending.date_hint,
        "payment_method_hint": pending.payment_method_hint,
        "category_hint": pending.category_hint,
    }
    missing_field_for_attribute = {
        "description": "description",
        "amount_raw": "amount",
        "installments": "installments",
        "date_hint": "date",
        "payment_method_hint": "payment_method",
        "category_hint": "category",
    }
    for attribute, value in protected_fields.items():
        is_still_confirmed = (
            missing_field_for_attribute[attribute] not in pending.missing_fields
        )
        if is_still_confirmed and payload[attribute] != value:
            return None
    if payload["amount_is_total"] != pending.amount_is_total:
        return None
    return ExtractedExpense.model_validate(payload)


async def resolve_pending_expenses(state: GraphState) -> dict:
    """Completa no máximo uma pendência e persiste usando a mensagem complementar."""

    active_pending = list(state.get("pending_expenses", []))
    expired_pending = list(state.get("expired_pending_expenses", []))
    user_id = state["user_id"]

    if not active_pending:
        return _finalize_cleared(
            format_expired_pending_message() if expired_pending else _NO_PENDING_MESSAGE
        )

    if _is_unambiguous_cancellation(state, active_pending):
        return _finalize_cleared(_CANCELLED_MESSAGE)

    try:
        categories = await list_available_categories(user_id)
    except Exception:
        logger.exception("pending_categories_load_failed", user_id)
        return _keep_all_pending(
            active_pending, _response_for_unmatched_pending(active_pending)
        )

    now = tools_calendar.user_now(state["user_timezone"])
    last_message = _last_user_message(state)
    decisions = [
        await _resolve_one_pending_expense(pending, last_message, now, categories)
        for pending in active_pending
    ]
    selected = [
        (pending, decision)
        for pending, decision in zip(active_pending, decisions, strict=True)
        if decision.status in {"completed", "cancelled"}
    ]

    if decisions and all(decision.status == "new_expense" for decision in decisions):
        return _resolution_state(
            route="add_new_expenses_agent",
            pending=active_pending,
            needs_clarification=True,
        )

    if len(selected) != 1:
        return _keep_all_pending(
            active_pending, _response_for_unmatched_pending(active_pending)
        )

    pending, decision = selected[0]
    remaining_pending = [item for item in active_pending if item.id != pending.id]
    if decision.status == "cancelled":
        return _finalize_one_resolved(remaining_pending, _CANCELLED_MESSAGE)

    if decision.expense is None:
        return _keep_all_pending(
            active_pending, _response_for_unmatched_pending(active_pending)
        )

    completed_expense = _merge_resolved_expense(pending, decision.expense)
    if completed_expense is None:
        return _keep_all_pending(active_pending, pending.clarification_message)

    outcome = resolve_extracted_expenses(
        [completed_expense], categories, state["user_timezone"], now
    )
    if not outcome.expenses:
        return _keep_all_pending(
            active_pending,
            decision.clarification_message or pending.clarification_message,
        )

    try:
        records: list[ExpenseRecord] = await insert_expenses(
            user_id=state["user_id"],
            expenses=outcome.expenses,
            source_message_id=state.get("message_id"),
        )
    except Exception:
        logger.exception("pending_expense_insert_failed", pending_id=pending.id)
        return _resolution_state(
            pending=active_pending,
            needs_clarification=True,
            clarification_message=pending.clarification_message,
            response_text=(
                "Não consegui salvar esse gasto agora. Pode tentar novamente?"
            ),
        )

    return _finalize_one_resolved(
        remaining_pending,
        format_confirmation(records),
        expense_details=outcome.expenses,
    )
