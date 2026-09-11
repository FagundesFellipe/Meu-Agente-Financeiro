"""ACL de saída: converte resultados de domínio em texto/dados seguros ao LLM."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import TypeAlias, cast

from financial_agent.agent.report.acl_in import (
    CategoryPendingSignal,
    ReportRequest,
)
from financial_agent.agent.report.format import format_brl, format_day_long
from financial_agent.agent.tools.payment_method import display_payment_method
from financial_agent.agent.tools.period import ResolvedPeriod
from shared.repositories.expense_reports import CategoryTotal
from shared.repositories.expenses import ExpenseRecord
from shared.repositories.recurring_expenses import RecurringExpenseRecord


@dataclass(frozen=True, slots=True)
class LineItem:
    amount: str
    description: str
    category: str
    day: str
    payment: str


@dataclass(frozen=True, slots=True)
class TotalPayload:
    kind: str
    period_label: str
    category_label: str | None
    payment_label: str | None
    total: str
    count: int
    is_empty: bool


@dataclass(frozen=True, slots=True)
class ComparePayload:
    kind: str
    unit: str
    a_label: str
    a_total: str
    a_count: int
    b_label: str
    b_total: str
    b_count: int
    a_top_expense: LineItem | None = None
    b_top_expense: LineItem | None = None
    a_top_category: str | None = None
    a_top_category_total: str | None = None
    a_top_category_expense: LineItem | None = None
    b_top_category: str | None = None
    b_top_category_total: str | None = None
    b_top_category_expense: LineItem | None = None


@dataclass(frozen=True, slots=True)
class ListPayload:
    kind: str
    period_label: str
    category_label: str | None
    payment_label: str | None
    lines: list[LineItem]
    total_count: int
    shown_count: int
    has_more: bool
    pagination_note: str


@dataclass(frozen=True, slots=True)
class CategoryBreakdownPayload:
    kind: str
    period_label: str
    payment_label: str | None
    rows: list[tuple[str, str]]
    grand_total: str
    is_empty: bool


@dataclass(frozen=True, slots=True)
class FixedExpensesPayload:
    kind: str
    rows: list[tuple[str, str, str, str]]
    is_empty: bool


@dataclass(frozen=True, slots=True)
class UnsupportedPayload:
    kind: str
    suggestions: list[str]


@dataclass(frozen=True, slots=True)
class CategoryClarificationPayload:
    kind: str
    asked_name: str
    suggestions: list[str]


@dataclass(frozen=True, slots=True)
class PeriodReportResult:
    period: ResolvedPeriod
    total: Decimal
    count: int
    top_expense: ExpenseRecord | None = None
    top_category: CategoryTotal | None = None
    top_category_expense: ExpenseRecord | None = None


@dataclass(frozen=True, slots=True)
class CategoryBreakdownResult:
    rows: list[CategoryTotal]
    grand_total: Decimal


ReportPayload: TypeAlias = (
    TotalPayload
    | ComparePayload
    | ListPayload
    | CategoryBreakdownPayload
    | FixedExpensesPayload
    | UnsupportedPayload
    | CategoryClarificationPayload
)
RawReportResult: TypeAlias = (
    tuple[Decimal, int]
    | list[PeriodReportResult]
    | tuple[list[ExpenseRecord], int]
    | CategoryBreakdownResult
    | list[RecurringExpenseRecord]
)

_UNSUPPORTED_SUGGESTIONS = [
    "Quanto gastei hoje?",
    "Quais foram meus últimos gastos?",
    "Compare esta semana com a passada.",
]


def _period_label(request: ReportRequest) -> str:
    return " + ".join(period.label for period in request.periods)


def _line(record: ExpenseRecord, now: datetime) -> LineItem:
    return LineItem(
        amount=format_brl(record.amount),
        description=record.description,
        category=record.category_name,
        day=format_day_long(record.occurred_at, now),
        payment=display_payment_method(record.payment_method),
    )


def _category_label(request: ReportRequest) -> str | None:
    return request.category.name if request.category else None


def _payment_label(request: ReportRequest) -> str | None:
    if request.payment_method is None:
        return None
    return display_payment_method(request.payment_method)


def build_total_payload(
    request: ReportRequest, result: tuple[Decimal, int]
) -> TotalPayload:
    total, count = result
    return TotalPayload(
        kind="total",
        period_label=_period_label(request),
        category_label=_category_label(request),
        payment_label=_payment_label(request),
        total=format_brl(total),
        count=count,
        is_empty=count == 0,
    )


def build_compare_payload(
    request: ReportRequest, result: list[PeriodReportResult], now: datetime
) -> ComparePayload:
    first, second = result
    weekly = first.period.unit == "week"
    return ComparePayload(
        kind="compare",
        unit=first.period.unit,
        a_label=first.period.label,
        a_total=format_brl(first.total),
        a_count=first.count,
        b_label=second.period.label,
        b_total=format_brl(second.total),
        b_count=second.count,
        a_top_expense=_line(first.top_expense, now)
        if weekly and first.top_expense
        else None,
        b_top_expense=_line(second.top_expense, now)
        if weekly and second.top_expense
        else None,
        a_top_category=first.top_category.category_name if first.top_category else None,
        a_top_category_total=(
            format_brl(first.top_category.total) if first.top_category else None
        ),
        a_top_category_expense=(
            _line(first.top_category_expense, now)
            if first.top_category_expense
            else None
        ),
        b_top_category=second.top_category.category_name
        if second.top_category
        else None,
        b_top_category_total=(
            format_brl(second.top_category.total) if second.top_category else None
        ),
        b_top_category_expense=(
            _line(second.top_category_expense, now)
            if second.top_category_expense
            else None
        ),
    )


def build_list_payload(
    request: ReportRequest,
    result: tuple[list[ExpenseRecord], int],
    now: datetime,
) -> ListPayload:
    rows, total_count = result
    limited = rows[: min(request.page_size, request.detail_cap)]
    lines = [_line(row, now) for row in limited]
    shown_count = len(lines)
    has_more = request.offset + shown_count < total_count
    note = f"Há {total_count} gastos nesse período; mostrando {shown_count}."
    return ListPayload(
        kind="list",
        period_label=_period_label(request),
        category_label=_category_label(request),
        payment_label=_payment_label(request),
        lines=lines,
        total_count=total_count,
        shown_count=shown_count,
        has_more=has_more,
        pagination_note=note,
    )


def build_category_breakdown_payload(
    request: ReportRequest, result: CategoryBreakdownResult
) -> CategoryBreakdownPayload:
    return CategoryBreakdownPayload(
        kind="category_breakdown",
        period_label=_period_label(request),
        payment_label=_payment_label(request),
        rows=[(row.category_name, format_brl(row.total)) for row in result.rows],
        grand_total=format_brl(result.grand_total),
        is_empty=not result.rows,
    )


def build_fixed_expenses_payload(
    result: list[RecurringExpenseRecord],
) -> FixedExpensesPayload:
    return FixedExpensesPayload(
        kind="fixed_expenses",
        rows=[
            (
                row.description,
                format_brl(row.amount),
                f"dia {row.recurrence_day}",
                row.category_name,
            )
            for row in result
        ],
        is_empty=not result,
    )


def build_unsupported_payload() -> UnsupportedPayload:
    return UnsupportedPayload(
        kind="unsupported", suggestions=list(_UNSUPPORTED_SUGGESTIONS)
    )


def build_category_clarification_payload(
    signal: CategoryPendingSignal,
) -> CategoryClarificationPayload:
    return CategoryClarificationPayload(
        kind="category_pending",
        asked_name=signal.asked_name,
        suggestions=signal.suggestions,
    )


def build_no_previous_list_payload() -> UnsupportedPayload:
    return UnsupportedPayload(
        kind="no_previous_list",
        suggestions=["Faça uma nova consulta, por exemplo: meus últimos gastos."],
    )


def build_payload(
    request: ReportRequest, result: RawReportResult, now: datetime
) -> ReportPayload:
    if request.operation == "total":
        return build_total_payload(request, cast(tuple[Decimal, int], result))
    if request.operation == "comparar_periodos":
        return build_compare_payload(
            request, cast(list[PeriodReportResult], result), now
        )
    if request.operation == "listar_gastos":
        return build_list_payload(
            request, cast(tuple[list[ExpenseRecord], int], result), now
        )
    if request.operation == "total_por_categoria":
        return build_category_breakdown_payload(
            request, cast(CategoryBreakdownResult, result)
        )
    return build_fixed_expenses_payload(cast(list[RecurringExpenseRecord], result))


def render_payload_for_llm(payload: ReportPayload) -> str:
    body = json.dumps(asdict(payload), ensure_ascii=False, indent=2)
    return f"PAYLOAD (única fonte de verdade — não calcule nada):\n{body}"


def fallback_text(payload: ReportPayload) -> str:
    """Resposta mínima determinística usada quando o LLM de redação falha."""
    if isinstance(payload, TotalPayload):
        if payload.is_empty:
            return f"Não houve gastos em {payload.period_label}."
        return f"Em {payload.period_label}, o total foi {payload.total}."
    if isinstance(payload, ListPayload):
        if not payload.lines:
            return f"Não houve gastos em {payload.period_label}."
        lines = [f"• {line.description}: {line.amount}" for line in payload.lines]
        return "\n".join([*lines, payload.pagination_note])
    if isinstance(payload, CategoryClarificationPayload):
        suggestions = ", ".join(payload.suggestions) or "uma categoria existente"
        return (
            f"Qual categoria você quis dizer com “{payload.asked_name}”? {suggestions}."
        )
    if isinstance(payload, UnsupportedPayload):
        return "Essa consulta ainda não está disponível. " + " ".join(
            payload.suggestions
        )
    if isinstance(payload, FixedExpensesPayload):
        if payload.is_empty:
            return "Você não tem gastos fixos ativos."
        return "\n".join(
            f"• {name}: {amount} ({day}, {category})"
            for name, amount, day, category in payload.rows
        )
    if isinstance(payload, CategoryBreakdownPayload):
        if payload.is_empty:
            return f"Não houve gastos em {payload.period_label}."
        return "\n".join(f"• {name}: {total}" for name, total in payload.rows)
    return (
        f"{payload.a_label}: {payload.a_total}. {payload.b_label}: {payload.b_total}."
    )
