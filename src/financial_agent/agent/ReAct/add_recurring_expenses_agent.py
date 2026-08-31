"""Sub-agente de cadastro de gastos fixos (regras mensais).

Divisão de responsabilidades, a mesma do registro de gasto pontual:

    LLM    -> extrai uma ou mais regras da mensagem em linguagem natural,
              normaliza o valor em algarismos e decide se falta informação
              para cadastrar. Só isso.
    Python -> converte valor para ``Decimal``, resolve o dia de recorrência e a
              data de início, normaliza meio de pagamento, resolve a categoria
              para um id real e persiste sem duplicar.

O que este agente **não** faz: listar, editar, desativar ou excluir regras;
criar categorias; e gerar os lançamentos mensais em ``expense`` — isso é da
Stack 2. Por isso a confirmação nunca promete lançamentos já criados.

Diferenças deliberadas em relação ao gasto pontual: não existe parcelamento
(uma regra mensal não é parcelada), não existe ``occurred_at`` (uma regra não
ocorreu) e categoria não resolvida **nunca** cai em uma categoria genérica —
vira pergunta ao usuário.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypedDict, cast

import structlog
from langchain.agents.structured_output import ToolStrategy

from financial_agent.agent.ReAct.add_new_expenses_agent import build_context_message
from financial_agent.agent.state_graph import (
    AddRecurringExpensesResult,
    ExtractedRecurringExpense,
    GraphState,
    PendingRecurringExpense,
    PendingRecurringExpenseField,
    RecurringExpenseDetails,
)
from financial_agent.agent.tools import amount_parser, get_category, payment_method
from financial_agent.agent.tools import calendar as tools_calendar
from financial_agent.agent.tools import recurrence as tools_recurrence
from financial_agent.agent.tools.pending_expenses import (
    assign_pending_metadata,
    format_pending_questions,
    keep_pending_metadata,
)
from shared.agent_builder import build_agent_for_version
from shared.prompt_loader import get_active_version
from shared.repositories.categories import CategoryRecord, list_available_categories
from shared.repositories.recurring_expenses import (
    InsertRecurringResult,
    RecurringExpenseRecord,
    insert_recurring_expenses,
)

logger = structlog.get_logger()

_ADD_RECURRING_EXPENSES_PROMPT_NAME = "ADD_RECURRING_EXPENSES_SYSTEM_PROMPT"

_NO_RECURRING_EXPENSE_FOUND = (
    "Não consegui identificar nenhum gasto fixo nessa mensagem. Me diga o que é, "
    "o valor mensal e em que dia do mês a cobrança acontece — por exemplo: "
    "“minha Netflix é 55 todo dia 10”."
)
_LLM_ERROR_MESSAGE = (
    "Desculpe, não consegui processar sua mensagem agora. Pode tentar novamente?"
)
_SAVE_FAILED_MESSAGE = (
    "Não consegui salvar esse gasto fixo agora. Pode tentar novamente?"
)


class AddRecurringStateDelta(TypedDict, total=False):
    """Patch de estado que este nó entrega ao grafo."""

    pending_recurring_expenses: list[PendingRecurringExpense]
    expired_pending_recurring_expenses: list[PendingRecurringExpense]
    recurring_expense_details: list[RecurringExpenseDetails]
    needs_clarification: bool
    clarification_message: str | None
    response_text: str | None


@dataclass(frozen=True, slots=True)
class RecurringResolutionOutcome:
    """Resultado do pós-processamento determinístico de uma extração."""

    recurring_expenses: list[RecurringExpenseDetails]
    pending_recurring_expenses: list[PendingRecurringExpense]


# ---- USER-FACING MESSAGES ----
def format_recurring_confirmation(records: list[RecurringExpenseRecord]) -> str:
    """Confirma as regras criadas, deixando claro que são cobranças mensais.

    Deliberadamente separada de ``format_confirmation`` do gasto pontual: aquela
    mensagem diz que um gasto foi anotado, e aqui nada foi gasto ainda.
    """
    if len(records) == 1:
        return f"Pronto! Registrei um gasto fixo mensal:\n{_describe_rule(records[0])}"

    lines = ["Pronto! Registrei estes gastos fixos mensais:"]
    lines += [_describe_rule(record) for record in records]

    return "\n".join(lines)


def format_duplicate_message(duplicates: list[RecurringExpenseRecord]) -> str:
    """Informa que a regra já existe, com o valor e o dia já cadastrados."""
    if len(duplicates) == 1:
        duplicate = duplicates[0]
        return (
            f"Você já tem {duplicate.description} cadastrado como gasto fixo de "
            f"R$ {duplicate.amount:.2f}, todo dia {duplicate.recurrence_day}."
        )

    lines = ["Estes gastos fixos já estavam cadastrados:"]
    lines += [_describe_rule(duplicate) for duplicate in duplicates]

    return "\n".join(lines)


def _describe_rule(record: RecurringExpenseRecord) -> str:
    return (
        f"• {record.description} — R$ {record.amount:.2f}, todo dia "
        f"{record.recurrence_day} ({record.category_name})."
    )


# ---- AGENT PROCESS ----
def build_add_recurring_expenses_agent() -> Any:
    """Constrói o agente de extração de regras a partir da versão ativa do prompt."""
    version = get_active_version(_ADD_RECURRING_EXPENSES_PROMPT_NAME)
    return build_agent_for_version(
        prompt_name=_ADD_RECURRING_EXPENSES_PROMPT_NAME,
        version=version,
        response_format=ToolStrategy(AddRecurringExpensesResult),
        agent_name="add_recurring_expenses_agent",
    )


def resolve_extracted_recurring_expenses(
    extracted: list[ExtractedRecurringExpense],
    categories: list[CategoryRecord],
    reference: datetime,
) -> RecurringResolutionOutcome:
    """Converte as extrações do LLM em regras prontas para persistir.

    Cada regra é resolvida isoladamente: uma incompleta vira pendência sem
    descartar as demais da mesma mensagem.
    """
    resolved: list[RecurringExpenseDetails] = []
    pending: list[PendingRecurringExpense] = []

    for candidate in extracted:
        details_or_pending = _resolve_one(candidate, categories, reference)
        if isinstance(details_or_pending, PendingRecurringExpense):
            pending.append(details_or_pending)
        else:
            resolved.append(details_or_pending)

    return RecurringResolutionOutcome(
        recurring_expenses=resolved,
        pending_recurring_expenses=pending,
    )


def _resolve_one(
    candidate: ExtractedRecurringExpense,
    categories: list[CategoryRecord],
    reference: datetime,
) -> RecurringExpenseDetails | PendingRecurringExpense:
    """Valida uma única regra; devolve o registro pronto ou a pergunta em aberto."""
    description = (candidate.description or "").strip()
    if not description:
        return _pending_from_candidate(
            candidate, "description", "Qual gasto fixo você quer cadastrar?"
        )

    try:
        amount = amount_parser.parse_expense_amount(candidate.amount_raw)
    except amount_parser.AmountParseError:
        return _pending_from_candidate(
            candidate, "amount", f"Qual é o valor mensal de “{description}”?"
        )

    try:
        recurrence_day = tools_recurrence.resolve_recurrence_day(
            candidate.recurrence_day_hint, reference
        )
    except tools_recurrence.RecurrenceResolutionError:
        return _pending_from_candidate(
            candidate,
            "recurrence_day",
            f"Em que dia do mês a cobrança de “{description}” acontece?",
        )

    # Categoria não resolvida nunca vira "Outros": um palpite genérico é
    # indistinguível de uma classificação correta depois de gravado (CON-014).
    category = get_category.find_category(
        description=description,
        hint=candidate.category_hint,
        categories=categories,
    )
    if category is None:
        return _pending_from_candidate(
            candidate,
            "category",
            f"Em que categoria eu classifico “{description}”?",
        )

    return RecurringExpenseDetails(
        description=description,
        original_description=description,
        amount=amount,
        category_id=category.id,
        category_name=category.name,
        payment_method=payment_method.normalize_payment_method(
            candidate.payment_method_hint
        ),
        recurrence_day=recurrence_day,
        starts_at=_resolve_starts_at_or_today(candidate.starts_at_hint, reference),
        confidence=candidate.confidence,
    )


def _resolve_starts_at_or_today(start_hint: str | None, reference: datetime):
    """Data de início da regra; um hint ilegível cai para hoje, sem pendência.

    ``starts_at`` não é campo obrigatório da tabela nem consta em
    ``PendingRecurringExpenseField``, então não há como perguntar por ele. Hoje
    é o mesmo default que a ausência do hint produz (CON-013), e a confirmação
    mostra a data para o usuário conferir.
    """
    try:
        return tools_recurrence.resolve_starts_at(start_hint, reference)
    except tools_recurrence.RecurrenceResolutionError:
        logger.warning("recurring_starts_at_unreadable", start_hint=start_hint)
        return reference.date()


def _pending_from_candidate(
    candidate: ExtractedRecurringExpense,
    missing_field: PendingRecurringExpenseField,
    question: str,
) -> PendingRecurringExpense:
    """Converte uma falha determinística em rascunho, nunca em persistência."""
    return PendingRecurringExpense(
        source_start=candidate.source_start,
        source_end=candidate.source_end,
        source_text=candidate.source_text,
        description=candidate.description or None,
        amount_raw=candidate.amount_raw or None,
        recurrence_day_hint=candidate.recurrence_day_hint,
        starts_at_hint=candidate.starts_at_hint,
        payment_method_hint=candidate.payment_method_hint,
        category_hint=candidate.category_hint,
        confidence=candidate.confidence,
        missing_fields=[missing_field],
        clarification_message=question,
    )


async def _extract(state: GraphState, context: Any) -> AddRecurringExpensesResult:
    agent = build_add_recurring_expenses_agent()
    try:
        result = await agent.ainvoke({"messages": [context, state["messages"][-1]]})
        return cast(AddRecurringExpensesResult, result["structured_response"])
    except Exception:
        # Fronteira de I/O: falha de rede/LLM não pode derrubar o nó.
        logger.exception(
            "recurring_llm_extraction_failed", user_id=state.get("user_id")
        )
        return AddRecurringExpensesResult(
            needs_clarification=True,
            clarification_message=_LLM_ERROR_MESSAGE,
        )


async def _persist(
    user_id: str,
    outcome: RecurringResolutionOutcome,
    message_id: str | None,
) -> InsertRecurringResult | None:
    """Grava as regras completas; ``None`` sinaliza falha de I/O."""
    if not outcome.recurring_expenses:
        return InsertRecurringResult(inserted=[], duplicates=[])

    try:
        return await insert_recurring_expenses(
            user_id=user_id,
            recurring_expenses=outcome.recurring_expenses,
            source_message_id=message_id,
        )
    except Exception:
        # Fronteira de I/O: falha ao gravar não pode derrubar o nó.
        logger.exception(
            "recurring_expense_insert_failed",
            user_id=user_id,
            recurring_expense_count=len(outcome.recurring_expenses),
        )
        return None


def _compose_response(
    insert_result: InsertRecurringResult | None, pending_text: str
) -> str:
    """Monta a resposta a partir do que de fato aconteceu com cada regra."""
    if insert_result is None:
        return _SAVE_FAILED_MESSAGE

    parts = []
    if insert_result.inserted:
        parts.append(format_recurring_confirmation(insert_result.inserted))
    if insert_result.duplicates:
        parts.append(format_duplicate_message(insert_result.duplicates))
    if pending_text:
        parts.append(pending_text)

    return "\n\n".join(parts) if parts else _NO_RECURRING_EXPENSE_FOUND


# ---- GRAPH NODE ----
async def add_recurring_expenses(state: GraphState) -> AddRecurringStateDelta:
    """Nó do grafo: extrai, valida e persiste as regras de gasto fixo da mensagem."""
    user_id = state["user_id"]

    try:
        categories = await list_available_categories(user_id)
    except Exception:
        # Fronteira de I/O: falha de banco/rede não pode derrubar o nó.
        logger.exception("recurring_categories_load_failed", user_id=user_id)
        return {"recurring_expense_details": [], "response_text": _LLM_ERROR_MESSAGE}

    now = tools_calendar.user_now(state["user_timezone"])
    extraction = await _extract(state, build_context_message(now, categories))

    if extraction.needs_clarification and not extraction.pending_recurring_expenses:
        return _keep_state_and_ask(
            state, extraction.clarification_message or _NO_RECURRING_EXPENSE_FOUND
        )

    outcome = resolve_extracted_recurring_expenses(
        extracted=extraction.recurring_expenses,
        categories=categories,
        reference=now,
    )
    insert_result = await _persist(user_id, outcome, state.get("message_id"))

    new_pending = assign_pending_metadata(extraction.pending_recurring_expenses, now)
    new_pending.extend(
        keep_pending_metadata(pending, now)
        for pending in outcome.pending_recurring_expenses
    )
    all_pending = [*state.get("pending_recurring_expenses", []), *new_pending]
    pending_text = format_pending_questions(new_pending)

    return {
        "pending_recurring_expenses": all_pending,
        "expired_pending_recurring_expenses": [],
        "recurring_expense_details": outcome.recurring_expenses,
        "needs_clarification": _has_open_question(state, all_pending),
        "clarification_message": pending_text or None,
        "response_text": _compose_response(insert_result, pending_text),
    }


def _keep_state_and_ask(state: GraphState, question: str) -> AddRecurringStateDelta:
    """Mantém as pendências existentes e devolve apenas a pergunta em aberto."""
    existing_pending = list(state.get("pending_recurring_expenses", []))
    return {
        "pending_recurring_expenses": existing_pending,
        "expired_pending_recurring_expenses": [],
        "recurring_expense_details": [],
        "needs_clarification": _has_open_question(state, existing_pending),
        "clarification_message": question,
        "response_text": question,
    }


def _has_open_question(
    state: GraphState, recurring_pending: list[PendingRecurringExpense]
) -> bool:
    """``needs_clarification`` é global: uma pendência pontual também conta."""
    return bool(recurring_pending or state.get("pending_expenses"))
