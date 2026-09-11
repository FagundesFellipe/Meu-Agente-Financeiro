"""ACL de saída do agente relator."""

import json
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from financial_agent.agent.report.acl_in import ReportRequest
from financial_agent.agent.report.acl_out import (
    CategoryBreakdownResult,
    PeriodReportResult,
    build_category_breakdown_payload,
    build_compare_payload,
    build_list_payload,
    build_total_payload,
    render_payload_for_llm,
)
from financial_agent.agent.tools.period import resolve_period
from shared.repositories.expense_reports import CategoryTotal
from shared.repositories.expenses import ExpenseRecord

NOW = datetime(2026, 8, 5, 14, 20, tzinfo=ZoneInfo("America/Sao_Paulo"))


def request(operation="total", periods=None, page_size=6, offset=0):
    return ReportRequest(
        operation=operation,
        periods=periods or [resolve_period("today", reference=NOW)],
        combination="merge",
        category=None,
        payment_method=None,
        page_size=page_size,
        offset=offset,
        detail_cap=15,
    )


def expense(amount: str, description: str, hour: int = 12) -> ExpenseRecord:
    return ExpenseRecord(
        id=uuid4(),
        amount=Decimal(amount),
        description=description,
        original_description=description,
        payment_method="pix",
        occurred_at=NOW.replace(hour=hour),
        category_id=uuid4(),
        category_name="Alimentação",
    )


def test_total_payload_formats_decimal_and_empty_state():
    payload = build_total_payload(request(), (Decimal("1234.56"), 2))

    assert payload.total == "R$ 1.234,56"
    assert payload.period_label == "hoje"
    assert payload.is_empty is False


def test_list_payload_applies_cap_without_changing_total_count():
    rows = [expense(str(index + 1), f"gasto {index}") for index in range(8)]

    payload = build_list_payload(request("listar_gastos", page_size=6), (rows, 14), NOW)

    assert len(payload.lines) == 6
    assert payload.total_count == 14
    assert payload.has_more is True
    assert payload.pagination_note == "Há 14 gastos nesse período; mostrando 6."


def test_week_comparison_exposes_top_expense_but_not_category():
    periods = [
        resolve_period("this_week", reference=NOW),
        resolve_period("last_week", reference=NOW),
    ]
    result = [
        PeriodReportResult(
            periods[0], Decimal("50"), 2, top_expense=expense("40", "mercado")
        ),
        PeriodReportResult(
            periods[1], Decimal("30"), 1, top_expense=expense("30", "uber")
        ),
    ]

    payload = build_compare_payload(request("comparar_periodos", periods), result, NOW)

    assert payload.a_top_expense.description == "mercado"
    assert payload.a_top_category is None


def test_month_comparison_exposes_top_category_and_its_expense():
    periods = [
        resolve_period("this_month", reference=NOW),
        resolve_period("last_month", reference=NOW),
    ]
    top = CategoryTotal(uuid4(), "Alimentação", Decimal("80"), 2)
    result = [
        PeriodReportResult(
            periods[0],
            Decimal("100"),
            3,
            top_category=top,
            top_category_expense=expense("60", "mercado"),
        ),
        PeriodReportResult(periods[1], Decimal("0"), 0),
    ]

    payload = build_compare_payload(request("comparar_periodos", periods), result, NOW)

    assert payload.a_top_category == "Alimentação"
    assert payload.a_top_category_total == "R$ 80,00"
    assert payload.a_top_category_expense.description == "mercado"


def test_category_breakdown_receives_grand_total_already_calculated():
    row = CategoryTotal(uuid4(), "Casa", Decimal("90"), 2)
    payload = build_category_breakdown_payload(
        request("total_por_categoria"),
        CategoryBreakdownResult([row], Decimal("90")),
    )

    assert payload.rows == [("Casa", "R$ 90,00")]
    assert payload.grand_total == "R$ 90,00"


def test_serialized_payload_is_the_only_source_of_truth_block():
    rendered = render_payload_for_llm(
        build_total_payload(request(), (Decimal("10"), 1))
    )

    assert rendered.startswith("PAYLOAD (única fonte de verdade")
    assert json.loads(rendered.split("\n", 1)[1])["total"] == "R$ 10,00"
