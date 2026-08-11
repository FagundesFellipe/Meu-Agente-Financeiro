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
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import structlog
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import SystemMessage

from financial_agent.agent.state_graph import (
    AddExpensesResult,
    ExpenseDetails,
    ExtractedExpense,
    GraphState,
)
from financial_agent.agent.tools import (
    amount_parser,
    get_category,
    payment_method,
)
from financial_agent.agent.tools import calendar as tools_calendar
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


@dataclass(frozen=True, slots=True)
class ResolutionOutcome:
    """Resultado do pós-processamento determinístico de uma extração."""

    expenses: list[ExpenseDetails]
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


def _expand_installments(
    base: ExpenseDetails, installments: int
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
                amount=base.amount,
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
    problems: list[str] = []

    for candidate in extracted:
        label = candidate.description or "gasto"
        try:
            amount = amount_parser.parse_amount(candidate.amount_raw)

            if (
                candidate.amount_is_total
                and candidate.installments
                and candidate.installments > 1
            ):
                amount = (amount / candidate.installments).quantize(Decimal("0.01"))

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
            problems.append(f"Qual foi o valor exato de “{label}”?")
            continue
        except tools_calendar.DateResolutionError:
            problems.append(f"Em que data foi o gasto de “{label}”?")
            continue
        except get_category.CategoryResolutionError as exc:
            problems.append(f"Não consegui categorizar “{label}” ({exc}).")
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
            resolved.extend(_expand_installments(base, installments))
        else:
            resolved.append(base)

    return ResolutionOutcome(expenses=resolved, problems=problems)


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

    pending = list(outcome.problems)
    if extraction.needs_clarification and extraction.clarification_message:
        pending.insert(0, extraction.clarification_message)

    if records and pending:
        response_text = format_confirmation(records) + "\n\n" + " ".join(pending)
    elif records:
        response_text = format_confirmation(records)
    elif pending:
        response_text = " ".join(pending)
    else:
        response_text = _NO_EXPENSE_FOUND

    return {
        "extracted_expenses": extraction.expenses,
        "expense_details": outcome.expenses,
        "response_text": response_text,
    }
