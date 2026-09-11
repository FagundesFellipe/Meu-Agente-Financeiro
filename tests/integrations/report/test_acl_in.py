"""ACL de entrada do agente relator."""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from financial_agent.agent.report.acl_in import (
    CategoryPendingSignal,
    PaginationWithoutContext,
    ReportRequest,
    resolve_report_request,
)
from financial_agent.agent.state_graph import (
    ExpenseQuery,
    Pagination,
    PeriodRef,
    ReportPageCursor,
)
from shared.repositories.categories import CategoryRecord

NOW = datetime(2026, 8, 5, 14, 20, tzinfo=ZoneInfo("America/Sao_Paulo"))


def category(name: str, personal: bool = False) -> CategoryRecord:
    return CategoryRecord(
        id=uuid4(),
        name=name,
        normalized_name=name.casefold(),
        description=None,
        is_personal=personal,
    )


def test_resolves_period_category_payment_and_page_size():
    food = category("Alimentação")
    query = ExpenseQuery(
        operation="listar_gastos",
        periods=[PeriodRef(symbol="this_month")],
        category="alimentacao",
        payment_method="pix",
        limit=10,
    )

    result = resolve_report_request(query, [food], "America/Sao_Paulo", NOW)

    assert isinstance(result, ReportRequest)
    assert result.periods[0].label == "este mês"
    assert result.category == food
    assert result.payment_method == "pix"
    assert result.page_size == 10
    assert result.offset == 0


def test_unresolved_category_becomes_clarification_with_global_suggestions():
    result = resolve_report_request(
        ExpenseQuery(
            operation="total",
            periods=[PeriodRef(symbol="this_week")],
            category="merc",
        ),
        [category("Mercado"), category("Mercadinho pessoal", personal=True)],
        "America/Sao_Paulo",
        NOW,
    )

    assert isinstance(result, CategoryPendingSignal)
    assert result.asked_name == "merc"
    assert result.suggestions == ["Mercado"]


def test_pagination_without_cursor_does_not_assume_a_query():
    query = ExpenseQuery(
        operation="listar_gastos", pagination=Pagination(intent="more")
    )

    result = resolve_report_request(query, [], "America/Sao_Paulo", NOW)

    assert isinstance(result, PaginationWithoutContext)


def test_pagination_rebuilds_filters_and_offset_from_cursor():
    food = category("Alimentação")
    cursor = ReportPageCursor(
        period_symbols=["this_month"],
        period_combination="merge",
        category_name="Alimentação",
        payment_method="credit_card",
        next_offset=6,
        total_count=20,
        created_at=NOW,
    )
    query = ExpenseQuery(
        operation="listar_gastos",
        pagination=Pagination(intent="more", extra_count=10),
    )

    result = resolve_report_request(query, [food], "America/Sao_Paulo", NOW, cursor)

    assert isinstance(result, ReportRequest)
    assert result.offset == 6
    assert result.page_size == 10
    assert result.category == food
    assert result.payment_method == "credit_card"
