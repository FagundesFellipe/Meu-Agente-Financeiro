"""Orquestração do nó real de consulta de gastos, sem rede ou banco."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import HumanMessage

from financial_agent.agent.build_graph_workflow import (
    build_workflow,
    route_decision_intentions,
)
from financial_agent.agent.ReAct import report_agent
from financial_agent.agent.report.acl_in import ReportRequest
from financial_agent.agent.report.acl_out import (
    CategoryClarificationPayload,
    ListPayload,
    TotalPayload,
    UnsupportedPayload,
    build_total_payload,
)
from financial_agent.agent.state_graph import (
    ExpenseQuery,
    Pagination,
    PeriodRef,
    ReportPageCursor,
)
from financial_agent.agent.tools.period import resolve_period
from shared.repositories.categories import CategoryRecord
from shared.repositories.expenses import ExpenseRecord

NOW = datetime(2026, 8, 5, 14, 20, tzinfo=ZoneInfo("America/Sao_Paulo"))


def state(message="quanto gastei hoje?"):
    return {
        "messages": [HumanMessage(content=message)],
        "phone_number": "5511999999999",
        "channel": "telegram",
        "user_id": str(uuid4()),
        "user_name": "Teste",
        "user_timezone": "America/Sao_Paulo",
        "message_id": str(uuid4()),
    }


def category(name="Alimentação"):
    return CategoryRecord(
        id=uuid4(),
        name=name,
        normalized_name="alimentacao",
        description=None,
        is_personal=False,
    )


def expense(index: int) -> ExpenseRecord:
    return ExpenseRecord(
        id=uuid4(),
        amount=Decimal(index + 1),
        description=f"gasto {index}",
        original_description=f"gasto {index}",
        payment_method="pix",
        occurred_at=NOW,
        category_id=uuid4(),
        category_name="Alimentação",
    )


def patch_boundaries(monkeypatch, query, raw_result, captured):
    async def fake_categories(_user_id):
        return [category()]

    async def fake_extract(_state, _now, _categories):
        return query

    async def fake_domain(_user_id, request):
        captured["request"] = request
        if isinstance(raw_result, Exception):
            raise raw_result
        return raw_result

    async def fake_verbalize(payload):
        captured["payload"] = payload
        return "resposta pronta"

    monkeypatch.setattr(report_agent, "list_available_categories", fake_categories)
    monkeypatch.setattr(report_agent, "_extract_query", fake_extract)
    monkeypatch.setattr(report_agent, "_run_domain", fake_domain)
    monkeypatch.setattr(report_agent, "_verbalize", fake_verbalize)
    monkeypatch.setattr(report_agent.tools_calendar, "user_now", lambda _tz: NOW)


@pytest.mark.asyncio
async def test_total_happy_path_builds_formatted_payload(monkeypatch):
    captured = {}
    patch_boundaries(
        monkeypatch,
        ExpenseQuery(operation="total", periods=[PeriodRef(symbol="today")]),
        (Decimal("35.50"), 1),
        captured,
    )

    result = await report_agent.view_expenses_report(state())

    assert result == {"response_text": "resposta pronta"}
    assert isinstance(captured["payload"], TotalPayload)
    assert captured["payload"].total == "R$ 35,50"


@pytest.mark.asyncio
async def test_list_creates_and_advances_cursor(monkeypatch):
    captured = {}
    query = ExpenseQuery(
        operation="listar_gastos", periods=[PeriodRef(symbol="this_month")]
    )
    patch_boundaries(monkeypatch, query, ([expense(i) for i in range(6)], 14), captured)

    result = await report_agent.view_expenses_report(state("meus últimos gastos"))

    assert isinstance(captured["payload"], ListPayload)
    assert result["report_page_cursor"].next_offset == 6
    assert result["report_page_cursor"].total_count == 14


@pytest.mark.asyncio
async def test_more_uses_previous_cursor_offset(monkeypatch):
    captured = {}
    query = ExpenseQuery(
        operation="listar_gastos", pagination=Pagination(intent="more")
    )
    patch_boundaries(monkeypatch, query, ([expense(i) for i in range(3)], 9), captured)
    current_state = state("mostre mais")
    current_state["report_page_cursor"] = ReportPageCursor(
        period_symbols=["this_month"],
        period_combination="merge",
        next_offset=6,
        total_count=9,
        created_at=NOW,
    )

    result = await report_agent.view_expenses_report(current_state)

    assert captured["request"].offset == 6
    assert result["report_page_cursor"].next_offset == 9


@pytest.mark.asyncio
async def test_more_without_cursor_returns_guidance(monkeypatch):
    captured = {}
    query = ExpenseQuery(
        operation="listar_gastos", pagination=Pagination(intent="more")
    )
    patch_boundaries(monkeypatch, query, ([], 0), captured)

    result = await report_agent.view_expenses_report(state("mostre mais"))

    assert result == {"response_text": "resposta pronta"}
    assert isinstance(captured["payload"], UnsupportedPayload)
    assert captured["payload"].kind == "no_previous_list"
    assert "request" not in captured


@pytest.mark.asyncio
async def test_unresolved_category_only_requests_clarification(monkeypatch):
    captured = {}
    query = ExpenseQuery(
        operation="total",
        periods=[PeriodRef(symbol="this_week")],
        category="categoria completamente diferente",
    )
    patch_boundaries(monkeypatch, query, (Decimal("0"), 0), captured)

    result = await report_agent.view_expenses_report(state())

    assert result == {"response_text": "resposta pronta"}
    assert isinstance(captured["payload"], CategoryClarificationPayload)
    assert "request" not in captured


@pytest.mark.asyncio
async def test_unsupported_is_recorded_without_running_domain(monkeypatch):
    captured = {}
    query = ExpenseQuery(
        operation="total", unsupported=True, unsupported_reason="previsão"
    )
    patch_boundaries(monkeypatch, query, (Decimal("0"), 0), captured)

    async def fake_record(**kwargs):
        captured["record"] = kwargs

    monkeypatch.setattr(report_agent, "insert_unsupported_query", fake_record)

    result = await report_agent.view_expenses_report(state("quanto vou gastar?"))

    assert result == {"response_text": "resposta pronta"}
    assert captured["record"]["raw_question"] == "quanto vou gastar?"
    assert captured["record"]["reason"] == "previsão"
    assert isinstance(captured["payload"], UnsupportedPayload)
    assert "request" not in captured


@pytest.mark.asyncio
async def test_extraction_failure_returns_fallback(monkeypatch):
    async def fake_categories(_user_id):
        return []

    async def fake_extract(*_args):
        return None

    monkeypatch.setattr(report_agent, "list_available_categories", fake_categories)
    monkeypatch.setattr(report_agent, "_extract_query", fake_extract)

    result = await report_agent.view_expenses_report(state())

    assert result == {"response_text": report_agent._FALLBACK}


@pytest.mark.asyncio
async def test_domain_failure_returns_fallback(monkeypatch):
    captured = {}
    patch_boundaries(
        monkeypatch,
        ExpenseQuery(operation="total", periods=[PeriodRef(symbol="today")]),
        RuntimeError("database unavailable"),
        captured,
    )

    result = await report_agent.view_expenses_report(state())

    assert result == {"response_text": report_agent._FALLBACK}


@pytest.mark.asyncio
async def test_unsupported_record_failure_does_not_block_response(monkeypatch):
    captured = {}
    query = ExpenseQuery(operation="total", unsupported=True)
    patch_boundaries(monkeypatch, query, (Decimal("0"), 0), captured)

    async def failing_record(**_kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(report_agent, "insert_unsupported_query", failing_record)

    result = await report_agent.view_expenses_report(state("minhas categorias"))

    assert result == {"response_text": "resposta pronta"}


@pytest.mark.asyncio
async def test_verbalization_failure_uses_python_fallback(monkeypatch):
    request = ReportRequest(
        operation="total",
        periods=[resolve_period("today", reference=NOW)],
        combination="merge",
        category=None,
        payment_method=None,
        page_size=0,
        offset=0,
        detail_cap=15,
    )
    payload = build_total_payload(request, (Decimal("10"), 1))
    monkeypatch.setattr(
        report_agent,
        "load_prompt_config",
        lambda _name: (_ for _ in ()).throw(RuntimeError("prompt unavailable")),
    )

    assert await report_agent._verbalize(payload) == "Em hoje, o total foi R$ 10,00."


def test_graph_routes_reports_to_the_real_node_and_compiles():
    assert route_decision_intentions({"intention": "view_expenses_report"}) == (
        "report_agent"
    )

    workflow = build_workflow()

    assert "report_agent" in workflow.nodes
    assert workflow.compile() is not None
