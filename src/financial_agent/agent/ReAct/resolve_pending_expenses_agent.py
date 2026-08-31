"""Nó que completa, cancela ou redireciona rascunhos de gastos pendentes."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypedDict, cast

import structlog
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from financial_agent.agent.ReAct.add_new_expenses_agent import (
    ResolutionOutcome,
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
_CHOOSE_WHICH_PENDING_MESSAGE = (
    "Tenho mais de uma pendência. Diga qual gasto você quer completar ou cancelar."
)
_NO_PENDING_MESSAGE = "Não encontrei uma pendência ativa. Envie o gasto completo."
_SAVE_FAILED_MESSAGE = "Não consegui salvar esse gasto agora. Pode tentar novamente?"
_CANCELLATION_PATTERN = re.compile(r"\b(cancelar|cancele|desisto|desistir)\b", re.I)
_ACTIONABLE_STATUSES: frozenset[str] = frozenset({"completed", "cancelled"})


class ResolvePendingStateDelta(TypedDict, total=False):
    """Patch de estado que este nó entrega ao grafo.

    ``response_text`` fica de fora quando o nó redireciona para
    ``add_new_expenses_agent``, que monta a resposta.
    """

    pending_expense_resolution_route: PendingExpenseResolutionRoute
    pending_expenses: list[PendingExpense]
    expired_pending_expenses: list[PendingExpense]
    needs_clarification: bool
    clarification_message: str | None
    expense_details: list[ExpenseDetails]
    response_text: str | None


class PendingResolutionDecision(BaseModel):
    """O que o modelo decidiu para um único rascunho, dada a resposta nova."""

    status: Literal["completed", "cancelled", "new_expense", "not_applicable"]
    expense: ExtractedExpense | None = None
    clarification_message: str | None = None


@dataclass(frozen=True, slots=True)
class _StateInputs:
    """A fatia de ``GraphState`` que este nó lê, desempacotada uma vez só."""

    user_id: str
    user_timezone: str
    message_id: str | None
    last_message: Any
    active_pending: list[PendingExpense]
    expired_pending: list[PendingExpense]


@dataclass(frozen=True, slots=True)
class _PromptInputs:
    """Os dados que cada tentativa de decisão injeta no prompt do modelo."""

    current_time: datetime
    last_message: Any
    categories: list[CategoryRecord]


# ---- ENTRY POINT ----
async def resolve_pending_expenses(state: GraphState) -> ResolvePendingStateDelta:
    """Trata a resposta do usuário a rascunhos pendentes.

    Completa um rascunho, cancela, redireciona para o registro normal ou
    apenas repete a pergunta em aberto — nunca mais de um por mensagem.
    """
    state_inputs = _read_state_inputs(state)

    if not state_inputs.active_pending:
        return _finalize_with_no_pending(_message_when_no_active_pending(state_inputs))

    if _is_unambiguous_cancellation(state_inputs):
        return _finalize_with_no_pending(_CANCELLED_MESSAGE)

    categories = await _load_categories_or_none(state_inputs.user_id)
    if categories is None:
        return _keep_pending_repeating_open_question(state_inputs.active_pending)

    prompt_inputs = _PromptInputs(
        current_time=tools_calendar.user_now(state_inputs.user_timezone),
        last_message=state_inputs.last_message,
        categories=categories,
    )
    decisions = await _decide_each_pending(state_inputs.active_pending, prompt_inputs)

    if _every_decision_is_new_expense(decisions):
        return _reroute_to_new_expense(state_inputs.active_pending)

    actionable_pairs = _actionable_decisions(state_inputs.active_pending, decisions)
    if len(actionable_pairs) != 1:
        return _keep_pending_repeating_open_question(state_inputs.active_pending)

    return await _apply_single_decision(
        actionable_pairs[0], state_inputs, prompt_inputs
    )


def _read_state_inputs(state: GraphState) -> _StateInputs:
    return _StateInputs(
        user_id=state["user_id"],
        user_timezone=state["user_timezone"],
        message_id=state.get("message_id"),
        last_message=state["messages"][-1],
        active_pending=list(state.get("pending_expenses", [])),
        expired_pending=list(state.get("expired_pending_expenses", [])),
    )


def _message_when_no_active_pending(state_inputs: _StateInputs) -> str:
    if state_inputs.expired_pending:
        return format_expired_pending_message()
    return _NO_PENDING_MESSAGE


def _is_unambiguous_cancellation(state_inputs: _StateInputs) -> bool:
    return len(state_inputs.active_pending) == 1 and bool(
        _CANCELLATION_PATTERN.search(_text_of_message(state_inputs.last_message))
    )


def _text_of_message(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", ""))


async def _load_categories_or_none(user_id: str) -> list[CategoryRecord] | None:
    """Carrega as categorias do usuário; ``None`` sinaliza falha de I/O."""
    try:
        return await list_available_categories(user_id)
    except Exception:
        # Fronteira de I/O: falha de banco/rede não pode derrubar o nó.
        logger.exception("pending_categories_load_failed", user_id=user_id)
        return None


async def _decide_each_pending(
    pending_expenses: list[PendingExpense], prompt_inputs: _PromptInputs
) -> list[PendingResolutionDecision]:
    return [
        await _resolve_one_pending_expense(pending_expense, prompt_inputs)
        for pending_expense in pending_expenses
    ]


def _every_decision_is_new_expense(
    decisions: list[PendingResolutionDecision],
) -> bool:
    return bool(decisions) and all(
        decision.status == "new_expense" for decision in decisions
    )


def _actionable_decisions(
    pending_expenses: list[PendingExpense],
    decisions: list[PendingResolutionDecision],
) -> list[tuple[PendingExpense, PendingResolutionDecision]]:
    """Pares (rascunho, decisão) que pedem completar ou cancelar o rascunho."""
    return [
        (pending_expense, decision)
        for pending_expense, decision in zip(pending_expenses, decisions, strict=True)
        if decision.status in _ACTIONABLE_STATUSES
    ]


async def _apply_single_decision(
    pending_and_decision: tuple[PendingExpense, PendingResolutionDecision],
    state_inputs: _StateInputs,
    prompt_inputs: _PromptInputs,
) -> ResolvePendingStateDelta:
    """Aplica a única decisão acionável — cancelar ou completar o rascunho."""
    target_pending, decision = pending_and_decision
    remaining_pending = _pending_expenses_without(
        state_inputs.active_pending, target_pending.id
    )

    if decision.status == "cancelled":
        return _finalize_with_remaining(remaining_pending, _CANCELLED_MESSAGE)

    if decision.expense is None:
        return _keep_pending_repeating_open_question(state_inputs.active_pending)

    accepted_expense = _accept_if_confirmed_fields_untouched(
        target_pending, decision.expense
    )
    if accepted_expense is None:
        return _keep_pending_and_ask(
            state_inputs.active_pending, target_pending.clarification_message
        )

    resolution_outcome = resolve_extracted_expenses(
        [accepted_expense],
        prompt_inputs.categories,
        state_inputs.user_timezone,
        prompt_inputs.current_time,
    )
    if not resolution_outcome.expenses:
        return _keep_pending_and_ask(
            state_inputs.active_pending,
            decision.clarification_message or target_pending.clarification_message,
        )

    return await _persist_resolved_expenses(
        target_pending, resolution_outcome, state_inputs
    )


async def _persist_resolved_expenses(
    target_pending: PendingExpense,
    resolution_outcome: ResolutionOutcome,
    state_inputs: _StateInputs,
) -> ResolvePendingStateDelta:
    try:
        saved_expenses: list[ExpenseRecord] = await insert_expenses(
            user_id=state_inputs.user_id,
            expenses=resolution_outcome.expenses,
            source_message_id=state_inputs.message_id,
        )
    except Exception:
        # Fronteira de I/O: falha ao gravar não pode derrubar o nó.
        logger.exception("pending_expense_insert_failed", pending_id=target_pending.id)
        return _build_state_delta(
            pending_expenses=state_inputs.active_pending,
            needs_clarification=True,
            clarification_message=target_pending.clarification_message,
            response_text=_SAVE_FAILED_MESSAGE,
        )

    remaining_pending = _pending_expenses_without(
        state_inputs.active_pending, target_pending.id
    )
    return _finalize_with_remaining(
        remaining_pending,
        format_confirmation(saved_expenses),
        expense_details=resolution_outcome.expenses,
    )


def _pending_expenses_without(
    pending_expenses: list[PendingExpense], pending_id: str | None
) -> list[PendingExpense]:
    return [
        pending_expense
        for pending_expense in pending_expenses
        if pending_expense.id != pending_id
    ]


# ---- LLM CALL FOR ONE PENDING ----
async def _resolve_one_pending_expense(
    pending_expense: PendingExpense, prompt_inputs: _PromptInputs
) -> PendingResolutionDecision:
    """Pede uma decisão para um único rascunho, isolado das demais conversas."""
    try:
        agent = build_pending_expense_resolution_agent()
        agent_output = await agent.ainvoke(
            {
                "messages": [
                    build_pending_resolution_prompt(
                        pending_expense,
                        prompt_inputs.current_time,
                        prompt_inputs.categories,
                    ),
                    prompt_inputs.last_message,
                ]
            }
        )
        return cast(PendingResolutionDecision, agent_output["structured_response"])
    except Exception:
        logger.exception(
            "pending_expense_resolution_failed", pending_id=pending_expense.id
        )
        return PendingResolutionDecision(status="not_applicable")


def build_pending_expense_resolution_agent() -> Any:
    """Constrói o agente dedicado, a partir do prompt cadastrado manualmente."""
    version = get_active_version(_PENDING_RESOLUTION_PROMPT_NAME)
    return build_agent_for_version(
        prompt_name=_PENDING_RESOLUTION_PROMPT_NAME,
        version=version,
        response_format=ToolStrategy(PendingResolutionDecision),
        agent_name="resolve_pending_expense_agent",
    )


def build_pending_resolution_prompt(
    pending_expense: PendingExpense,
    current_time: datetime,
    categories: list[CategoryRecord],
) -> SystemMessage:
    """Monta o único bloco de contexto permitido para uma tentativa de resolução."""
    return SystemMessage(
        content=(
            "# CONTEXTO_DE_PENDENCIA\n"
            f"DATA_HORA_ATUAL: {current_time.isoformat()}\n"
            f"RASCUNHO_PENDENTE: {pending_expense.model_dump_json()}\n"
            "CATEGORIAS_DISPONIVEIS:\n"
            f"{format_categories_for_prompt(categories)}"
        )
    )


# ---- DOMAIN GUARD ----
def _accept_if_confirmed_fields_untouched(
    pending_expense: PendingExpense, proposed_expense: ExtractedExpense
) -> ExtractedExpense | None:
    """Devolve a proposta só se ela não alterou nenhum campo já confirmado."""
    proposed_values = proposed_expense.model_dump()
    confirmed_value_by_field = {
        "description": pending_expense.description,
        "amount_raw": pending_expense.amount_raw,
        "installments": pending_expense.installments,
        "date_hint": pending_expense.date_hint,
        "payment_method_hint": pending_expense.payment_method_hint,
        "category_hint": pending_expense.category_hint,
    }
    missing_field_name_by_attribute = {
        "description": "description",
        "amount_raw": "amount",
        "installments": "installments",
        "date_hint": "date",
        "payment_method_hint": "payment_method",
        "category_hint": "category",
    }
    for attribute, confirmed_value in confirmed_value_by_field.items():
        is_still_confirmed = (
            missing_field_name_by_attribute[attribute]
            not in pending_expense.missing_fields
        )
        if is_still_confirmed and proposed_values[attribute] != confirmed_value:
            return None
    if proposed_values["amount_is_total"] != pending_expense.amount_is_total:
        return None
    return ExtractedExpense.model_validate(proposed_values)


# ---- STATE-DELTA BUILDERS ----
def _build_state_delta(
    *,
    pending_expenses: list[PendingExpense],
    needs_clarification: bool,
    route: PendingExpenseResolutionRoute = "finalize_response",
    clarification_message: str | None = None,
    response_text: str | None = None,
    expense_details: list[ExpenseDetails] | None = None,
) -> ResolvePendingStateDelta:
    """Contrato de retorno deste nó, montado num lugar só.

    ``expired_pending_expenses`` é sempre zerado: pendências expiradas já
    foram tratadas antes deste nó. ``response_text`` só entra no dicionário
    quando informado.
    """
    state_delta: ResolvePendingStateDelta = {
        "pending_expense_resolution_route": route,
        "pending_expenses": pending_expenses,
        "expired_pending_expenses": [],
        "needs_clarification": needs_clarification,
        "clarification_message": clarification_message,
        "expense_details": expense_details or [],
    }
    if response_text is not None:
        state_delta["response_text"] = response_text
    return state_delta


def _finalize_with_no_pending(response_text: str) -> ResolvePendingStateDelta:
    """Encerra o fluxo sem nenhuma pendência restante."""
    return _build_state_delta(
        pending_expenses=[],
        needs_clarification=False,
        response_text=response_text,
    )


def _reroute_to_new_expense(
    active_pending: list[PendingExpense],
) -> ResolvePendingStateDelta:
    """Devolve o controle ao registro normal, mantendo as pendências."""
    return _build_state_delta(
        route="add_new_expenses_agent",
        pending_expenses=active_pending,
        needs_clarification=True,
    )


def _keep_pending_repeating_open_question(
    active_pending: list[PendingExpense],
) -> ResolvePendingStateDelta:
    """Nada casou: mantém as pendências e repete a pergunta em aberto."""
    return _keep_pending_and_ask(
        active_pending, _message_for_unmatched_pending(active_pending)
    )


def _keep_pending_and_ask(
    active_pending: list[PendingExpense], clarification_question: str
) -> ResolvePendingStateDelta:
    """Mantém as pendências como estão e repete a pergunta informada."""
    return _build_state_delta(
        pending_expenses=active_pending,
        needs_clarification=True,
        clarification_message=clarification_question,
        response_text=clarification_question,
    )


def _finalize_with_remaining(
    remaining_pending: list[PendingExpense],
    primary_message: str,
    expense_details: list[ExpenseDetails] | None = None,
) -> ResolvePendingStateDelta:
    """Fecha após resolver um rascunho, anexando a próxima pergunta em aberto."""
    return _build_state_delta(
        pending_expenses=remaining_pending,
        needs_clarification=bool(remaining_pending),
        clarification_message=format_pending_questions(remaining_pending) or None,
        response_text=_append_next_pending_question(primary_message, remaining_pending),
        expense_details=expense_details,
    )


def _append_next_pending_question(
    primary_message: str, remaining_pending: list[PendingExpense]
) -> str:
    next_question = format_pending_questions(remaining_pending)
    if next_question:
        return f"{primary_message}\n\n{next_question}"
    return primary_message


def _message_for_unmatched_pending(active_pending: list[PendingExpense]) -> str:
    if len(active_pending) > 1:
        return _CHOOSE_WHICH_PENDING_MESSAGE
    return format_pending_questions(active_pending)
