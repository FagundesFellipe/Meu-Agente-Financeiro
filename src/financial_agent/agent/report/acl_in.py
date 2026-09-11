"""ACL de entrada: transforma a extração do LLM em pedido de domínio seguro."""

from dataclasses import dataclass
from datetime import datetime
from typing import cast

from financial_agent.agent.state_graph import (
    ExpenseQuery,
    PaymentMethod,
    PeriodCombination,
    PeriodRef,
    PeriodSymbol,
    ReportOperation,
    ReportPageCursor,
)
from financial_agent.agent.tools.calendar import DateResolutionError
from financial_agent.agent.tools.get_category import (
    find_category,
    suggest_similar_categories,
)
from financial_agent.agent.tools.payment_method import normalize_payment_method
from financial_agent.agent.tools.period import (
    PeriodResolutionError,
    ResolvedPeriod,
    resolve_period,
)
from shared.config import settings
from shared.repositories.categories import CategoryRecord


@dataclass(frozen=True, slots=True)
class ReportRequest:
    operation: ReportOperation
    periods: list[ResolvedPeriod]
    combination: PeriodCombination
    category: CategoryRecord | None
    payment_method: PaymentMethod | None
    page_size: int
    offset: int
    detail_cap: int


@dataclass(frozen=True, slots=True)
class CategoryPendingSignal:
    asked_name: str
    suggestions: list[str]


@dataclass(frozen=True, slots=True)
class PaginationWithoutContext:
    pass


@dataclass(frozen=True, slots=True)
class InvalidRequest:
    reason: str


ReportResolution = (
    ReportRequest | CategoryPendingSignal | PaginationWithoutContext | InvalidRequest
)


def _period_ref_from_cursor(value: str) -> PeriodRef:
    if value.startswith("specific_day:"):
        return PeriodRef(symbol="specific_day", day_hint=value.split(":", 1)[1])
    return PeriodRef(symbol=cast(PeriodSymbol, value))


def _category_signal(
    name: str, categories: list[CategoryRecord]
) -> CategoryPendingSignal:
    return CategoryPendingSignal(
        asked_name=name,
        suggestions=suggest_similar_categories(
            name, categories, settings.report_similar_categories
        ),
    )


def _resolve_category(
    name: str | None, categories: list[CategoryRecord]
) -> CategoryRecord | CategoryPendingSignal | None:
    if name is None:
        return None
    category = find_category(description="", hint=name, categories=categories)
    return category if category is not None else _category_signal(name, categories)


def _resolve_periods(
    refs: list[PeriodRef], timezone: str, now: datetime
) -> list[ResolvedPeriod] | InvalidRequest:
    try:
        return [
            resolve_period(
                period.symbol,
                day_hint=period.day_hint,
                timezone=timezone,
                reference=now,
            )
            for period in refs
        ]
    except (PeriodResolutionError, DateResolutionError):
        return InvalidRequest("período ilegível")


def _validate_comparison(
    query: ExpenseQuery, periods: list[ResolvedPeriod]
) -> InvalidRequest | None:
    if query.operation != "comparar_periodos":
        return None
    if len(periods) != 2 or len({period.unit for period in periods}) != 1:
        return InvalidRequest("comparação exige dois períodos da mesma unidade")
    return None


def _request_from_cursor(
    query: ExpenseQuery,
    categories: list[CategoryRecord],
    timezone: str,
    now: datetime,
    cursor: ReportPageCursor,
) -> ReportResolution:
    try:
        refs = [_period_ref_from_cursor(value) for value in cursor.period_symbols]
    except (ValueError, TypeError):
        return InvalidRequest("cursor de paginação inválido")
    periods = _resolve_periods(refs, timezone, now)
    if isinstance(periods, InvalidRequest):
        return periods
    category = _resolve_category(cursor.category_name, categories)
    if isinstance(category, CategoryPendingSignal):
        return category
    requested_size = query.pagination.extra_count if query.pagination else None
    page_size = min(
        requested_size or settings.report_page_size,
        settings.report_detail_max_lines,
    )
    return ReportRequest(
        operation="listar_gastos",
        periods=periods,
        combination="merge",
        category=category,
        payment_method=cursor.payment_method,
        page_size=page_size,
        offset=cursor.next_offset,
        detail_cap=settings.report_detail_max_lines,
    )


def resolve_report_request(
    query: ExpenseQuery,
    categories: list[CategoryRecord],
    timezone: str,
    now: datetime,
    prev_cursor: ReportPageCursor | None = None,
) -> ReportResolution:
    """Valida e resolve o contrato externo sem permitir decisão do LLM no SQL."""
    if query.pagination is not None:
        if prev_cursor is None:
            return PaginationWithoutContext()
        return _request_from_cursor(query, categories, timezone, now, prev_cursor)

    periods = _resolve_periods(query.periods, timezone, now)
    if isinstance(periods, InvalidRequest):
        return periods
    invalid_comparison = _validate_comparison(query, periods)
    if invalid_comparison:
        return invalid_comparison
    category = _resolve_category(query.category, categories)
    if isinstance(category, CategoryPendingSignal):
        return category
    payment_method = (
        normalize_payment_method(query.payment_method)
        if query.payment_method is not None
        else None
    )
    page_size = 0
    if query.operation == "listar_gastos":
        page_size = min(
            query.limit or settings.report_page_size,
            settings.report_detail_max_lines,
        )
    return ReportRequest(
        operation=query.operation,
        periods=periods,
        combination=query.period_combination,
        category=category,
        payment_method=payment_method,
        page_size=page_size,
        offset=0,
        detail_cap=settings.report_detail_max_lines,
    )
