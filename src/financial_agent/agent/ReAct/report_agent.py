"""Nó do agente relator: LLMs nas bordas e domínio determinístico no centro."""

import asyncio
from datetime import datetime
from typing import Any, cast

import structlog
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage, SystemMessage

from financial_agent.agent.middleware.trim import trim_messages_by_turns
from financial_agent.agent.report.acl_in import (
    CategoryPendingSignal,
    InvalidRequest,
    PaginationWithoutContext,
    ReportRequest,
    resolve_report_request,
)
from financial_agent.agent.report.acl_out import (
    CategoryBreakdownResult,
    PeriodReportResult,
    RawReportResult,
    ReportPayload,
    build_category_clarification_payload,
    build_no_previous_list_payload,
    build_payload,
    build_unsupported_payload,
    fallback_text,
    render_payload_for_llm,
)
from financial_agent.agent.state_graph import (
    ExpenseQuery,
    GraphState,
    ReportPageCursor,
)
from financial_agent.agent.tools import calendar as tools_calendar
from financial_agent.agent.tools.get_category import normalize
from financial_agent.agent.tools.period import ResolvedPeriod
from shared.agent_builder import build_agent_for_version
from shared.config import settings
from shared.llm import create_chat_model, get_model_id
from shared.prompt_loader import get_active_version, load_prompt_config
from shared.repositories.categories import (
    CategoryRecord,
    format_categories_for_prompt,
    list_available_categories,
)
from shared.repositories.expense_reports import (
    largest_category_with_top_expense,
    largest_expense,
    list_expenses_page_for_periods,
    sum_by_category_for_periods,
    sum_expenses,
    sum_expenses_for_periods,
)
from shared.repositories.recurring_expenses import (
    list_active_recurring_expenses_sorted,
)
from shared.repositories.unsupported_queries import insert_unsupported_query

logger = structlog.get_logger()

_QUERY_PROMPT_NAME = "REPORT_QUERY_EXTRACTION"
_RESPONSE_PROMPT_NAME = "REPORT_RESPONSE"
_FALLBACK = "Desculpe, não consegui consultar seus gastos agora. Tente novamente."


def build_report_query_agent() -> Any:
    version = get_active_version(_QUERY_PROMPT_NAME)
    return build_agent_for_version(
        prompt_name=_QUERY_PROMPT_NAME,
        version=version,
        response_format=ToolStrategy(ExpenseQuery),
        agent_name="report_query_agent",
    )


def _build_context_message(
    now: datetime, categories: list[CategoryRecord]
) -> SystemMessage:
    content = "\n".join(
        [
            "# CONTEXTO",
            f"DATA_HORA_ATUAL: {now.isoformat()}",
            "INICIO_DA_SEMANA: segunda-feira",
            "",
            "CATEGORIAS_DISPONIVEIS:",
            format_categories_for_prompt(categories),
        ]
    )
    return SystemMessage(content=content)


async def _extract_query(
    state: GraphState,
    now: datetime,
    categories: list[CategoryRecord],
) -> ExpenseQuery | None:
    try:
        history = trim_messages_by_turns(
            state["messages"], keep_turns=settings.report_history_turns
        )
        result = await build_report_query_agent().ainvoke(
            {"messages": [_build_context_message(now, categories), *history]}
        )
        return cast(ExpenseQuery, result["structured_response"])
    except Exception:
        logger.exception("report_extraction_failed", user_id=state.get("user_id"))
        return None


async def _verbalize(payload: ReportPayload) -> str:
    try:
        config = load_prompt_config(_RESPONSE_PROMPT_NAME)
        model = create_chat_model(
            get_model_id(config["llm_model"]),
            config.get("llm_temperature"),
            config.get("llm_reasoning_effort"),
        )
        response = await model.ainvoke(
            [
                SystemMessage(content=config["prompt_content"]),
                HumanMessage(content=render_payload_for_llm(payload)),
            ]
        )
        return str(response.content)
    except Exception:
        logger.exception("report_verbalization_failed", payload_kind=payload.kind)
        return fallback_text(payload)


async def _comparison_result(
    user_id: str, request: ReportRequest
) -> list[PeriodReportResult]:
    category_id = request.category.id if request.category else None
    results: list[PeriodReportResult] = []
    for period in request.periods:
        total, count = await sum_expenses(
            user_id,
            period.start,
            period.end,
            category_id,
            request.payment_method,
        )
        if period.unit == "week":
            top_expense = await largest_expense(
                user_id,
                period.start,
                period.end,
                category_id,
                request.payment_method,
            )
            results.append(
                PeriodReportResult(period, total, count, top_expense=top_expense)
            )
            continue
        if period.unit == "day":
            results.append(PeriodReportResult(period, total, count))
            continue
        top_category, top_expense = await largest_category_with_top_expense(
            user_id,
            period.start,
            period.end,
            category_id,
            request.payment_method,
        )
        results.append(
            PeriodReportResult(
                period,
                total,
                count,
                top_category=top_category,
                top_category_expense=top_expense,
            )
        )
    return results


async def _run_domain(user_id: str, request: ReportRequest) -> RawReportResult:
    category_id = request.category.id if request.category else None
    if request.operation == "total":
        return await sum_expenses_for_periods(
            user_id, request.periods, category_id, request.payment_method
        )
    if request.operation == "comparar_periodos":
        return await _comparison_result(user_id, request)
    if request.operation == "listar_gastos":
        return await list_expenses_page_for_periods(
            user_id,
            request.periods,
            category_id,
            request.payment_method,
            request.page_size,
            request.offset,
        )
    if request.operation == "total_por_categoria":
        rows_task = sum_by_category_for_periods(
            user_id, request.periods, request.payment_method
        )
        total_task = sum_expenses_for_periods(
            user_id, request.periods, payment_method=request.payment_method
        )
        rows, (grand_total, _) = await asyncio.gather(rows_task, total_task)
        return CategoryBreakdownResult(rows=rows, grand_total=grand_total)
    return await list_active_recurring_expenses_sorted(user_id)


def _last_human_text(state: GraphState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
        if isinstance(message, dict) and message.get("role") in {"human", "user"}:
            return str(message.get("content", ""))
    return ""


async def _safe_record_unsupported(
    state: GraphState,
    query: ExpenseQuery,
    reason: str | None = None,
) -> None:
    raw_question = _last_human_text(state)
    try:
        await insert_unsupported_query(
            user_id=state["user_id"],
            raw_question=raw_question,
            intent="view_expenses_report",
            normalized_question=normalize(raw_question),
            source_message_id=state.get("message_id"),
            reason=reason or query.unsupported_reason,
        )
    except Exception:
        logger.exception(
            "unsupported_report_query_record_failed", user_id=state.get("user_id")
        )


def _cursor_symbol(period: ResolvedPeriod) -> str:
    labels = {
        "hoje": "today",
        "ontem": "yesterday",
        "esta semana": "this_week",
        "semana passada": "last_week",
        "este mês": "this_month",
        "mês passado": "last_month",
    }
    return labels.get(period.label, f"specific_day:{period.label}")


def _make_cursor(
    request: ReportRequest,
    result: tuple[list[Any], int],
    now: datetime,
) -> ReportPageCursor:
    rows, total_count = result
    shown_count = min(len(rows), request.page_size, request.detail_cap)
    return ReportPageCursor(
        period_symbols=[_cursor_symbol(period) for period in request.periods],
        period_combination=request.combination,
        category_name=request.category.name if request.category else None,
        payment_method=request.payment_method,
        next_offset=request.offset + shown_count,
        total_count=total_count,
        created_at=now,
    )


async def _resolve_special_response(resolution) -> str | None:
    if isinstance(resolution, CategoryPendingSignal):
        return await _verbalize(build_category_clarification_payload(resolution))
    if isinstance(resolution, PaginationWithoutContext):
        return await _verbalize(build_no_previous_list_payload())
    return None


async def view_expenses_report(state: GraphState) -> dict:
    user_id = state["user_id"]
    now = tools_calendar.user_now(state["user_timezone"])
    try:
        categories = await list_available_categories(user_id)
    except Exception:
        logger.exception("report_categories_load_failed", user_id=user_id)
        return {"response_text": _FALLBACK}

    query = await _extract_query(state, now, categories)
    if query is None:
        return {"response_text": _FALLBACK}
    if query.unsupported:
        await _safe_record_unsupported(state, query)
        return {"response_text": await _verbalize(build_unsupported_payload())}

    resolution = resolve_report_request(
        query,
        categories,
        state["user_timezone"],
        now,
        state.get("report_page_cursor"),
    )
    special_response = await _resolve_special_response(resolution)
    if special_response is not None:
        return {"response_text": special_response}
    if isinstance(resolution, InvalidRequest):
        await _safe_record_unsupported(state, query, resolution.reason)
        return {"response_text": await _verbalize(build_unsupported_payload())}
    request = cast(ReportRequest, resolution)

    try:
        raw_result = await _run_domain(user_id, request)
    except Exception:
        logger.exception(
            "report_domain_failed", user_id=user_id, operation=request.operation
        )
        return {"response_text": _FALLBACK}

    payload = build_payload(request, raw_result, now)
    delta: dict[str, Any] = {"response_text": await _verbalize(payload)}
    if request.operation == "listar_gastos":
        delta["report_page_cursor"] = _make_cursor(
            request,
            cast(tuple[list[Any], int], raw_result),
            now,
        )
    return delta
