"""Sub-agente de registro de gastos.

Divisão de responsabilidades (deliberada):

    LLM    -> extrai gastos da mensagem em linguagem natural, normaliza o
              valor em algarismos, identifica parcelamentos e decide se
              falta informação para registrar. Só isso.
    Python -> converte valor para ``Decimal``, resolve data no fuso do usuário,
              normaliza meio de pagamento, resolve a categoria para um id real,
              expande parcelamentos em múltiplos registros e persiste com
              idempotência.

O agente é construído com ``create_agent`` mesmo sem tools expostas: a resposta
estruturada vem por ``ToolStrategy`` e a estrutura já fica pronta para receber
as tools do fluxo de correção (``get_last_expense``, ``update_expense``) sem
reescrita.

Correção de gasto ainda não é suportada — o prompt instrui o modelo a devolver
``needs_clarification`` explicando isso ao usuário.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any, cast

import structlog
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import SystemMessage

from financial_agent.agent.state_graph import (
    AddExpensesResult,
    ExpenseDetails,
    ExtractedExpense,
    GraphState,
    PendingExpense,
    PendingExpenseField,
)
from financial_agent.agent.tools import (
    amount_parser,
    get_category,
    payment_method,
)
from financial_agent.agent.tools import calendar as tools_calendar
from financial_agent.agent.tools.pending_expenses import (
    assign_pending_metadata,
    format_pending_questions,
    keep_pending_metadata,
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

_NO_EXPENSE_FOUND = (
    "Não consegui identificar nenhum gasto nessa mensagem. Me diga o que você "
    "gastou e o valor, por exemplo: “gastei 35 no almoço”."
)

_LLM_ERROR_MESSAGE = (
    "Desculpe, não consegui processar sua mensagem agora. Pode tentar novamente?"
)

_INCONSISTENT_EXTRACTION_MESSAGE = (
    "Não consegui identificar com segurança qual gasto precisa de esclarecimento. "
    "Pode reenviar a informação com descrição e valor?"
)


@dataclass(frozen=True, slots=True)
class ResolutionOutcome:
    """Resultado do pós-processamento determinístico de uma extração."""

    expenses: list[ExpenseDetails]
    pending_expenses: list[PendingExpense]
    problems: list[str]


_ADD_EXPENSES_PROMPT_NAME = "ADD_EXPENSES"


# ---- HELPER FUNCTIONS ----
def _add_months(dt: datetime, months: int) -> datetime:
    """Adiciona ``months`` meses a ``dt``, clampando o dia se necessário.

    Preserva hora, minuto, segundo e fuso do datetime original.
    Ex.: 31/01 + 1 mês -> 28/02 (ou 29 em ano bissexto).
    """
    year = dt.year
    month = dt.month + months
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


def format_confirmation(records: list[ExpenseRecord]) -> str:
    """Mensagem de confirmação enviada ao usuário após gravar os gastos."""
    if len(records) == 1:
        record = records[0]
        return (
            f"Anotado: {record.description} — R$ {record.amount:.2f} "
            f"({record.category_name})."
        )

    total = sum(record.amount for record in records)
    lines = ["Anotei estes gastos:"]
    lines += [
        f"• {r.description} — R$ {r.amount:.2f} ({r.category_name})" for r in records
    ]
    lines.append(f"Total: R$ {total:.2f}")

    return "\n".join(lines)


def build_context_message(
    now: datetime, categories: list[CategoryRecord]
) -> SystemMessage:
    """Monta o bloco de contexto exigido pelo prompt (data atual + categorias)."""
    lines = ["# CONTEXTO", f"DATA_HORA_ATUAL: {now.isoformat()}"]
    lines += ["", "CATEGORIAS_DISPONIVEIS:", format_categories_for_prompt(categories)]

    return SystemMessage(content="\n".join(lines))


def _split_total_into_installments(total: Decimal, installments: int) -> list[Decimal]:
    """Divide ``total`` em ``installments`` parcelas cujo somatório bate exato.

    A divisão em centavos raramente é exata (ex.: 5000 / 12 = 416,6666...), então
    a parcela base é arredondada para baixo e o resto em centavos é distribuído,
    um centavo por parcela, a partir da primeira — em vez de arredondar cada
    parcela isoladamente e deixar o total derivar do valor informado.
    """
    base_amount = (total / installments).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    remainder_cents = int((total - base_amount * installments) / Decimal("0.01"))

    amounts = [base_amount] * installments
    for i in range(remainder_cents):
        amounts[i] += Decimal("0.01")
    return amounts


def _expand_installments(
    base: ExpenseDetails, installments: int, amounts: list[Decimal]
) -> list[ExpenseDetails]:
    """Expande um gasto parcelado em um registro por parcela.

    A parcela 1 usa a data base (validada, sem futuro). As parcelas 2+ têm
    datas calculadas deterministicamente via :func:`_add_months` — essas datas
    são futuras por natureza do parcelamento, o que é uma exceção lógica à
    regra "data futura não é aceita".
    """
    if installments <= 1:
        return [base]

    expanded: list[ExpenseDetails] = []
    for i in range(installments):
        occurred_at = base.occurred_at if i == 0 else _add_months(base.occurred_at, i)
        expanded.append(
            ExpenseDetails(
                description=f"{base.description} ({i + 1}/{installments})",
                original_description=base.original_description,
                amount=amounts[i],
                occurred_at=occurred_at,
                category_id=base.category_id,
                category_name=base.category_name,
                payment_method=base.payment_method,
                installment_number=i + 1,
                total_installments=installments,
                confidence=base.confidence,
            )
        )
    return expanded


def _pending_from_candidate(
    candidate: ExtractedExpense,
    missing_field: PendingExpenseField,
    question: str,
) -> PendingExpense:
    """Converte uma falha determinística em rascunho, nunca em persistência."""
    return PendingExpense(
        description=candidate.description or None,
        source_start=candidate.source_start,
        source_end=candidate.source_end,
        source_text=candidate.source_text,
        amount_raw=candidate.amount_raw or None,
        installments=candidate.installments,
        amount_is_total=candidate.amount_is_total,
        date_hint=candidate.date_hint,
        time_hint=candidate.time_hint,
        payment_method_hint=candidate.payment_method_hint,
        category_hint=candidate.category_hint,
        confidence=candidate.confidence,
        missing_fields=[missing_field],
        clarification_message=question,
    )


def _last_message_content(state: GraphState) -> str:
    message = state["messages"][-1]
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", ""))


def _extraction_has_overlapping_items(
    extraction: AddExpensesResult, source_message: str
) -> bool:
    """Exige faixas válidas e disjuntas quando há itens claros e pendentes."""
    if not extraction.expenses or not extraction.pending_expenses:
        return False

    spans = [
        (item.source_start, item.source_end, item.source_text)
        for item in [*extraction.expenses, *extraction.pending_expenses]
    ]
    if any(
        start is None
        or end is None
        or not text
        or start >= end
        or end > len(source_message)
        or source_message[start:end] != text
        for start, end, text in spans
    ):
        return True

    normalized_spans = [
        (start, end) for start, end, _ in spans if start is not None and end is not None
    ]
    spans_overlap = any(
        first_start < second_end and second_start < first_end
        for index, (first_start, first_end) in enumerate(normalized_spans)
        for second_start, second_end in normalized_spans[index + 1 :]
    )
    return spans_overlap or any(
        not _source_text_substantiates_item(item, source_text)
        for item, (_, _, source_text) in zip(
            [*extraction.expenses, *extraction.pending_expenses], spans, strict=True
        )
    )


def _source_text_substantiates_item(
    item: ExtractedExpense | PendingExpense, source_text: str | None
) -> bool:
    """Confere se a faixa informa os dados conhecidos do próprio gasto.

    Isso impede que o modelo divida uma compra ambígua em um registro claro e
    uma pendência sobre um sufixo sem relação, apenas para produzir faixas
    disjuntas.
    """
    if not source_text:
        return False

    normalized_source = re.sub(r"[^\w]", "", source_text.casefold())
    normalized_description = re.sub(r"[^\w]", "", (item.description or "").casefold())
    normalized_amount = re.sub(r"\D", "", item.amount_raw or "")
    source_digits = re.sub(r"\D", "", source_text)

    return (
        bool(normalized_description or normalized_amount)
        and (not normalized_description or normalized_description in normalized_source)
        and (not normalized_amount or normalized_amount in source_digits)
    )


# ---- AGENT PROCESS ----
def build_add_expenses_agent() -> Any:
    """Constrói o agente de extração de gastos.

    Lê a versão ativa do prompt e delega para o builder cacheado em
    :mod:`shared.agent_builder`. Qualquer alteração feita pelo
    ``prompts_manager`` (que sempre cria uma nova versão) é detectada
    automaticamente — sem precisar reiniciar o processo.
    """
    version = get_active_version(_ADD_EXPENSES_PROMPT_NAME)
    return build_agent_for_version(
        prompt_name=_ADD_EXPENSES_PROMPT_NAME,
        version=version,
        response_format=ToolStrategy(AddExpensesResult),
        agent_name="add_new_expenses_agent",
    )


def resolve_extracted_expenses(
    extracted: list[ExtractedExpense],
    categories: list[CategoryRecord],
    timezone: str,
    reference: datetime | None = None,
) -> ResolutionOutcome:
    """Converte as extrações do LLM em gastos prontos para persistir.

    Cada gasto é resolvido isoladamente: um item ilegível vira um problema
    reportado ao usuário, sem descartar os demais — é a regra do PRD de que
    itens inequívocos da mesma mensagem continuam sendo salvos.
    """
    resolved: list[ExpenseDetails] = []
    pending_expenses: list[PendingExpense] = []
    problems: list[str] = []

    for candidate in extracted:
        label = candidate.description or "gasto"
        try:
            amount = amount_parser.parse_amount(candidate.amount_raw)

            occurred_at = tools_calendar.resolve_occurred_at(
                date_hint=candidate.date_hint,
                time_hint=candidate.time_hint,
                timezone=timezone,
                reference=reference,
            )
            category = get_category.resolve_category(
                description=candidate.description,
                hint=candidate.category_hint,
                categories=categories,
            )
        except amount_parser.AmountParseError:
            question = f"Qual foi o valor exato de “{label}”?"
            pending_expenses.append(
                _pending_from_candidate(candidate, "amount", question)
            )
            problems.append(question)
            continue
        except tools_calendar.DateResolutionError:
            question = f"Em que data foi o gasto de “{label}”?"
            pending_expenses.append(
                _pending_from_candidate(candidate, "date", question)
            )
            problems.append(question)
            continue
        except get_category.CategoryResolutionError as exc:
            question = f"Não consegui categorizar “{label}” ({exc})."
            pending_expenses.append(
                _pending_from_candidate(candidate, "category", question)
            )
            problems.append(question)
            continue

        base = ExpenseDetails(
            description=candidate.description.strip(),
            original_description=candidate.description.strip(),
            amount=amount,
            occurred_at=occurred_at,
            category_id=category.id,
            category_name=category.name,
            payment_method=payment_method.normalize_payment_method(
                candidate.payment_method_hint
            ),
            confidence=candidate.confidence,
        )

        installments = candidate.installments
        if installments and installments > 1:
            amounts = (
                _split_total_into_installments(amount, installments)
                if candidate.amount_is_total
                else [amount] * installments
            )
            resolved.extend(_expand_installments(base, installments, amounts))
        else:
            resolved.append(base)

    return ResolutionOutcome(
        expenses=resolved,
        pending_expenses=pending_expenses,
        problems=problems,
    )


async def _extract(state: GraphState, context: SystemMessage) -> AddExpensesResult:
    agent = build_add_expenses_agent()
    try:
        last_message = state["messages"][-1]

        result = await agent.ainvoke({"messages": [context, last_message]})
        return cast(AddExpensesResult, result["structured_response"])
    except Exception:
        logger.exception("llm_extraction_failed", user_id=state.get("user_id"))
        return AddExpensesResult(
            expenses=[],
            needs_clarification=True,
            clarification_message=_LLM_ERROR_MESSAGE,
        )


# --- GRAPH NODE ----
async def add_new_expenses(state: GraphState) -> dict:
    """Nó do grafo: extrai, valida e persiste os gastos da mensagem do usuário."""

    user_id = state["user_id"]
    user_timezone = state["user_timezone"]

    try:
        categories = await list_available_categories(user_id)
    except Exception:
        logger.exception("categories_load_failed", user_id=user_id)
        return {
            "extracted_expenses": [],
            "expense_details": [],
            "response_text": _LLM_ERROR_MESSAGE,
        }

    now = tools_calendar.user_now(user_timezone)

    extraction = await _extract(state, build_context_message(now, categories))

    existing_pending = list(state.get("pending_expenses", []))
    if (
        extraction.needs_clarification and not extraction.pending_expenses
    ) or _extraction_has_overlapping_items(extraction, _last_message_content(state)):
        return {
            "extracted_expenses": [],
            "pending_expenses": existing_pending,
            "expired_pending_expenses": [],
            "needs_clarification": bool(existing_pending),
            "clarification_message": _INCONSISTENT_EXTRACTION_MESSAGE,
            "expense_details": [],
            "response_text": _INCONSISTENT_EXTRACTION_MESSAGE,
        }

    outcome = resolve_extracted_expenses(
        extracted=extraction.expenses,
        categories=categories,
        timezone=user_timezone,
        reference=now,
    )

    records: list[ExpenseRecord] = []
    if outcome.expenses:
        try:
            records = await insert_expenses(
                user_id=user_id,
                expenses=outcome.expenses,
                source_message_id=state.get("message_id"),
            )
        except Exception:
            logger.exception(
                "expense_insert_failed",
                user_id=user_id,
                expense_count=len(outcome.expenses),
            )
            records = []

    new_pending = assign_pending_metadata(extraction.pending_expenses, now)
    new_pending.extend(
        keep_pending_metadata(pending, now) for pending in outcome.pending_expenses
    )
    all_pending = [*existing_pending, *new_pending]
    pending_text = format_pending_questions(new_pending)

    if records and pending_text:
        response_text = format_confirmation(records) + "\n\n" + pending_text
    elif records:
        response_text = format_confirmation(records)
    elif pending_text:
        response_text = pending_text
    else:
        response_text = _NO_EXPENSE_FOUND

    return {
        "extracted_expenses": extraction.expenses,
        "pending_expenses": all_pending,
        "expired_pending_expenses": [],
        "needs_clarification": bool(all_pending),
        "clarification_message": pending_text or None,
        "expense_details": outcome.expenses,
        "response_text": response_text,
    }
