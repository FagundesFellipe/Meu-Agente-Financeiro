"""Nó que completa, cancela ou redireciona rascunhos de gastos fixos pendentes.

Espelha ``resolve_pending_expenses_agent`` na estrutura, mas não o reusa: o
guard de campos confirmados de lá conhece ``installments``, ``date_hint`` e
``amount_is_total``, que não existem em uma regra mensal, e sua aplicação
chama ``insert_expenses``. O que é genuinamente comum — TTL, metadados e o
guard genérico — vem de ``tools/pending_expenses.py``.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypedDict, cast

import structlog
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from financial_agent.agent.ReAct.add_recurring_expenses_agent import (
    RecurringResolutionOutcome,
    format_duplicate_message,
    format_recurring_confirmation,
    resolve_extracted_recurring_expenses,
)
from financial_agent.agent.state_graph import (
    ExtractedRecurringExpense,
    GraphState,
    PendingRecurringExpense,
    PendingRecurringExpenseResolutionRoute,
    RecurringExpenseDetails,
)
from financial_agent.agent.tools import calendar as tools_calendar
from financial_agent.agent.tools.pending_expenses import (
    accept_if_confirmed_fields_untouched,
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
from shared.repositories.recurring_expenses import (
    InsertRecurringResult,
    insert_recurring_expenses,
)

logger = structlog.get_logger()

_PENDING_RESOLUTION_PROMPT_NAME = "RESOLVE_PENDING_RECURRING_EXPENSE"

_CANCELLED_MESSAGE = "Certo, cancelei essa pendência. Nenhum gasto fixo foi cadastrado."
_CHOOSE_WHICH_PENDING_MESSAGE = (
    "Tenho mais de um gasto fixo pendente. Diga qual deles você quer completar "
    "ou cancelar."
)
_NO_PENDING_MESSAGE = (
    "Não encontrei um gasto fixo pendente. Envie a regra completa, com o valor "
    "mensal e o dia da cobrança."
)
_SAVE_FAILED_MESSAGE = (
    "Não consegui salvar esse gasto fixo agora. Pode tentar novamente?"
)
_CANCELLATION_PATTERN = re.compile(r"\b(cancelar|cancele|desisto|desistir)\b", re.I)
_ACTIONABLE_STATUSES: frozenset[str] = frozenset({"completed", "cancelled"})

# ``amount_raw`` aparece como ``amount`` em missing_fields, e
# ``recurrence_day_hint`` como ``recurrence_day``.
_MISSING_FIELD_NAME_BY_ATTRIBUTE = {
    "description": "description",
    "amount_raw": "amount",
    "recurrence_day_hint": "recurrence_day",
    "category_hint": "category",
}


class ResolvePendingRecurringStateDelta(TypedDict, total=False):
    """Patch de estado que este nó entrega ao grafo.

    ``response_text`` fica de fora quando o nó redireciona para
    ``add_recurring_expenses_agent``, que monta a resposta.
    """

    pending_recurring_expense_resolution_route: PendingRecurringExpenseResolutionRoute
    pending_recurring_expenses: list[PendingRecurringExpense]
    expired_pending_recurring_expenses: list[PendingRecurringExpense]
    needs_clarification: bool
    clarification_message: str | None
    recurring_expense_details: list[RecurringExpenseDetails]
    response_text: str | None


class PendingRecurringResolutionDecision(BaseModel):
    """O que o modelo decidiu para um único rascunho, dada a resposta nova."""

    status: Literal["completed", "cancelled", "new_recurring_expense", "not_applicable"]
    recurring_expense: ExtractedRecurringExpense | None = None
    clarification_message: str | None = None


@dataclass(frozen=True, slots=True)
class _StateInputs:
    """A fatia de ``GraphState`` que este nó lê, desempacotada uma vez só."""

    user_id: str
    user_timezone: str
    message_id: str | None
    last_message: Any
    active_pending: list[PendingRecurringExpense]
    expired_pending: list[PendingRecurringExpense]
    has_pending_expense: bool


@dataclass(frozen=True, slots=True)
class _PromptInputs:
    """Os dados que cada tentativa de decisão injeta no prompt do modelo."""

    current_time: datetime
    last_message: Any
    categories: list[CategoryRecord]


# ---- ENTRY POINT ----
async def resolve_pending_recurring_expenses(
    state: GraphState,
) -> ResolvePendingRecurringStateDelta:
    """Trata a resposta do usuário a rascunhos de gasto fixo pendentes.

    Completa um rascunho, cancela, redireciona para o cadastro normal ou apenas
    repete a pergunta em aberto — nunca mais de um por mensagem.
    """
    state_inputs = _read_state_inputs(state)

    if not state_inputs.active_pending:
        return _finalize_with_no_pending(
            state_inputs, _message_when_no_active_pending(state_inputs)
        )

    if _is_unambiguous_cancellation(state_inputs):
        return _finalize_with_no_pending(state_inputs, _CANCELLED_MESSAGE)

    categories = await _load_categories_or_none(state_inputs.user_id)
    if categories is None:
        return _keep_pending_repeating_open_question(state_inputs)

    prompt_inputs = _PromptInputs(
        current_time=tools_calendar.user_now(state_inputs.user_timezone),
        last_message=state_inputs.last_message,
        categories=categories,
    )
    decisions = await _decide_each_pending(state_inputs.active_pending, prompt_inputs)

    if _every_decision_is_new_recurring_expense(decisions):
        return _reroute_to_new_recurring_expense(state_inputs)

    actionable_pairs = _actionable_decisions(state_inputs.active_pending, decisions)
    if len(actionable_pairs) != 1:
        return _keep_pending_repeating_open_question(state_inputs)

    return await _apply_single_decision(
        actionable_pairs[0], state_inputs, prompt_inputs
    )


def _read_state_inputs(state: GraphState) -> _StateInputs:
    return _StateInputs(
        user_id=state["user_id"],
        user_timezone=state["user_timezone"],
        message_id=state.get("message_id"),
        last_message=state["messages"][-1],
        active_pending=list(state.get("pending_recurring_expenses", [])),
        expired_pending=list(state.get("expired_pending_recurring_expenses", [])),
        has_pending_expense=bool(state.get("pending_expenses")),
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
        logger.exception("pending_recurring_categories_load_failed", user_id=user_id)
        return None


async def _decide_each_pending(
    pending_expenses: list[PendingRecurringExpense], prompt_inputs: _PromptInputs
) -> list[PendingRecurringResolutionDecision]:
    return [
        await _resolve_one_pending_recurring_expense(pending_expense, prompt_inputs)
        for pending_expense in pending_expenses
    ]


def _every_decision_is_new_recurring_expense(
    decisions: list[PendingRecurringResolutionDecision],
) -> bool:
    return bool(decisions) and all(
        decision.status == "new_recurring_expense" for decision in decisions
    )


def _actionable_decisions(
    pending_expenses: list[PendingRecurringExpense],
    decisions: list[PendingRecurringResolutionDecision],
) -> list[tuple[PendingRecurringExpense, PendingRecurringResolutionDecision]]:
    """Pares (rascunho, decisão) que pedem completar ou cancelar o rascunho."""
    return [
        (pending_expense, decision)
        for pending_expense, decision in zip(pending_expenses, decisions, strict=True)
        if decision.status in _ACTIONABLE_STATUSES
    ]


async def _apply_single_decision(
    pending_and_decision: tuple[
        PendingRecurringExpense, PendingRecurringResolutionDecision
    ],
    state_inputs: _StateInputs,
    prompt_inputs: _PromptInputs,
) -> ResolvePendingRecurringStateDelta:
    """Aplica a única decisão acionável — cancelar ou completar o rascunho."""
    target_pending, decision = pending_and_decision
    remaining_pending = _pending_without(state_inputs.active_pending, target_pending.id)

    if decision.status == "cancelled":
        return _finalize_with_remaining(
            state_inputs, remaining_pending, _CANCELLED_MESSAGE
        )

    if decision.recurring_expense is None:
        return _keep_pending_repeating_open_question(state_inputs)

    accepted = _accept_if_confirmed_fields_untouched(
        target_pending, decision.recurring_expense
    )
    if accepted is None:
        return _keep_pending_and_ask(state_inputs, target_pending.clarification_message)

    resolution_outcome = resolve_extracted_recurring_expenses(
        extracted=[accepted],
        categories=prompt_inputs.categories,
        reference=prompt_inputs.current_time,
    )
    if not resolution_outcome.recurring_expenses:
        return _keep_pending_and_ask(
            state_inputs,
            decision.clarification_message or target_pending.clarification_message,
        )

    return await _persist_resolved_recurring_expenses(
        target_pending, resolution_outcome, state_inputs
    )


async def _persist_resolved_recurring_expenses(
    target_pending: PendingRecurringExpense,
    resolution_outcome: RecurringResolutionOutcome,
    state_inputs: _StateInputs,
) -> ResolvePendingRecurringStateDelta:
    try:
        insert_result: InsertRecurringResult = await insert_recurring_expenses(
            user_id=state_inputs.user_id,
            recurring_expenses=resolution_outcome.recurring_expenses,
            source_message_id=state_inputs.message_id,
        )
    except Exception:
        # Fronteira de I/O: falha ao gravar não pode derrubar o nó.
        logger.exception(
            "pending_recurring_expense_insert_failed", pending_id=target_pending.id
        )
        return _keep_pending_and_ask(
            state_inputs,
            _SAVE_FAILED_MESSAGE,
            clarification_from_pending=target_pending,
        )

    remaining_pending = _pending_without(state_inputs.active_pending, target_pending.id)
    return _finalize_with_remaining(
        state_inputs,
        remaining_pending,
        _message_for_insert_result(insert_result),
        recurring_expense_details=resolution_outcome.recurring_expenses,
    )


def _message_for_insert_result(insert_result: InsertRecurringResult) -> str:
    if insert_result.inserted:
        return format_recurring_confirmation(insert_result.inserted)
    return format_duplicate_message(insert_result.duplicates)


def _pending_without(
    pending_expenses: list[PendingRecurringExpense], pending_id: str | None
) -> list[PendingRecurringExpense]:
    return [
        pending_expense
        for pending_expense in pending_expenses
        if pending_expense.id != pending_id
    ]


# ---- LLM CALL FOR ONE PENDING ----
async def _resolve_one_pending_recurring_expense(
    pending_expense: PendingRecurringExpense, prompt_inputs: _PromptInputs
) -> PendingRecurringResolutionDecision:
    """Pede uma decisão para um único rascunho, isolado das demais conversas."""
    try:
        agent = build_pending_recurring_resolution_agent()
        agent_output = await agent.ainvoke(
            {
                "messages": [
                    build_pending_recurring_resolution_prompt(
                        pending_expense,
                        prompt_inputs.current_time,
                        prompt_inputs.categories,
                    ),
                    prompt_inputs.last_message,
                ]
            }
        )
        return cast(
            PendingRecurringResolutionDecision, agent_output["structured_response"]
        )
    except Exception:
        # Fronteira de I/O: falha de rede/LLM não pode derrubar o nó.
        logger.exception(
            "pending_recurring_expense_resolution_failed",
            pending_id=pending_expense.id,
        )
        return PendingRecurringResolutionDecision(status="not_applicable")


def build_pending_recurring_resolution_agent() -> Any:
    """Constrói o agente dedicado, a partir do prompt cadastrado no manager."""
    version = get_active_version(_PENDING_RESOLUTION_PROMPT_NAME)
    return build_agent_for_version(
        prompt_name=_PENDING_RESOLUTION_PROMPT_NAME,
        version=version,
        response_format=ToolStrategy(PendingRecurringResolutionDecision),
        agent_name="resolve_pending_recurring_expense_agent",
    )


def build_pending_recurring_resolution_prompt(
    pending_expense: PendingRecurringExpense,
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
    pending_expense: PendingRecurringExpense,
    proposed: ExtractedRecurringExpense,
) -> ExtractedRecurringExpense | None:
    """Devolve a proposta só se ela não alterou nenhum campo já confirmado."""
    return accept_if_confirmed_fields_untouched(
        proposal=proposed,
        confirmed_value_by_attribute={
            "description": pending_expense.description,
            "amount_raw": pending_expense.amount_raw,
            "recurrence_day_hint": pending_expense.recurrence_day_hint,
            "category_hint": pending_expense.category_hint,
        },
        missing_field_name_by_attribute=_MISSING_FIELD_NAME_BY_ATTRIBUTE,
        still_missing_fields=pending_expense.missing_fields,
    )


# ---- STATE-DELTA BUILDERS ----
def _build_state_delta(
    *,
    state_inputs: _StateInputs,
    pending_recurring_expenses: list[PendingRecurringExpense],
    route: PendingRecurringExpenseResolutionRoute = "finalize_response",
    clarification_message: str | None = None,
    response_text: str | None = None,
    recurring_expense_details: list[RecurringExpenseDetails] | None = None,
) -> ResolvePendingRecurringStateDelta:
    """Contrato de retorno deste nó, montado num lugar só.

    ``expired_pending_recurring_expenses`` é sempre zerado: pendências expiradas
    já foram tratadas antes deste nó. ``response_text`` só entra no dicionário
    quando informado.
    """
    state_delta: ResolvePendingRecurringStateDelta = {
        "pending_recurring_expense_resolution_route": route,
        "pending_recurring_expenses": pending_recurring_expenses,
        "expired_pending_recurring_expenses": [],
        "needs_clarification": bool(
            pending_recurring_expenses or state_inputs.has_pending_expense
        ),
        "clarification_message": clarification_message,
        "recurring_expense_details": recurring_expense_details or [],
    }
    if response_text is not None:
        state_delta["response_text"] = response_text
    return state_delta


def _finalize_with_no_pending(
    state_inputs: _StateInputs, response_text: str
) -> ResolvePendingRecurringStateDelta:
    """Encerra o fluxo sem nenhuma pendência de gasto fixo restante."""
    return _build_state_delta(
        state_inputs=state_inputs,
        pending_recurring_expenses=[],
        response_text=response_text,
    )


def _reroute_to_new_recurring_expense(
    state_inputs: _StateInputs,
) -> ResolvePendingRecurringStateDelta:
    """Devolve o controle ao cadastro normal, mantendo as pendências."""
    return _build_state_delta(
        state_inputs=state_inputs,
        route="add_recurring_expenses_agent",
        pending_recurring_expenses=state_inputs.active_pending,
    )


def _keep_pending_repeating_open_question(
    state_inputs: _StateInputs,
) -> ResolvePendingRecurringStateDelta:
    """Nada casou: mantém as pendências e repete a pergunta em aberto."""
    return _keep_pending_and_ask(
        state_inputs, _message_for_unmatched_pending(state_inputs.active_pending)
    )


def _keep_pending_and_ask(
    state_inputs: _StateInputs,
    response_text: str,
    clarification_from_pending: PendingRecurringExpense | None = None,
) -> ResolvePendingRecurringStateDelta:
    """Mantém as pendências como estão e responde com a mensagem informada.

    ``clarification_from_pending`` separa os dois casos em que a resposta ao
    usuário não é a própria pergunta: uma falha ao gravar responde o erro, mas
    a pergunta em aberto continua sendo a do rascunho.
    """
    clarification_message = (
        clarification_from_pending.clarification_message
        if clarification_from_pending is not None
        else response_text
    )
    return _build_state_delta(
        state_inputs=state_inputs,
        pending_recurring_expenses=state_inputs.active_pending,
        clarification_message=clarification_message,
        response_text=response_text,
    )


def _finalize_with_remaining(
    state_inputs: _StateInputs,
    remaining_pending: list[PendingRecurringExpense],
    primary_message: str,
    recurring_expense_details: list[RecurringExpenseDetails] | None = None,
) -> ResolvePendingRecurringStateDelta:
    """Fecha após resolver um rascunho, anexando a próxima pergunta em aberto."""
    next_question = format_pending_questions(remaining_pending)
    return _build_state_delta(
        state_inputs=state_inputs,
        pending_recurring_expenses=remaining_pending,
        clarification_message=next_question or None,
        response_text=(
            f"{primary_message}\n\n{next_question}"
            if next_question
            else primary_message
        ),
        recurring_expense_details=recurring_expense_details,
    )


def _message_for_unmatched_pending(
    active_pending: list[PendingRecurringExpense],
) -> str:
    if len(active_pending) > 1:
        return _CHOOSE_WHICH_PENDING_MESSAGE
    return format_pending_questions(active_pending)
