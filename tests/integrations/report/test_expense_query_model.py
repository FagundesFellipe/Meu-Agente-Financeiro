"""Contratos estruturados do agente relator."""

import pytest
from pydantic import ValidationError

from financial_agent.agent.state_graph import ExpenseQuery, Pagination, PeriodRef


def test_total_requires_a_period():
    with pytest.raises(ValidationError):
        ExpenseQuery(operation="total")


def test_compare_requires_two_periods_of_the_same_unit():
    query = ExpenseQuery(
        operation="comparar_periodos",
        period_combination="compare",
        periods=[PeriodRef(symbol="this_week"), PeriodRef(symbol="last_week")],
    )

    assert len(query.periods) == 2

    with pytest.raises(ValidationError):
        ExpenseQuery(
            operation="comparar_periodos",
            period_combination="compare",
            periods=[PeriodRef(symbol="this_week"), PeriodRef(symbol="last_month")],
        )


def test_specific_day_and_day_hint_are_coupled():
    assert PeriodRef(symbol="specific_day", day_hint="22/07").day_hint == "22/07"

    with pytest.raises(ValidationError):
        PeriodRef(symbol="specific_day")
    with pytest.raises(ValidationError):
        PeriodRef(symbol="today", day_hint="22/07")


def test_pagination_is_only_allowed_for_expense_lists():
    query = ExpenseQuery(
        operation="listar_gastos", pagination=Pagination(intent="more")
    )

    assert query.periods == []

    with pytest.raises(ValidationError):
        ExpenseQuery(
            operation="total",
            periods=[PeriodRef(symbol="today")],
            pagination=Pagination(intent="more"),
        )


def test_fixed_expenses_reject_every_filter():
    assert ExpenseQuery(operation="listar_gastos_fixos").periods == []

    with pytest.raises(ValidationError):
        ExpenseQuery(operation="listar_gastos_fixos", payment_method="credit_card")


def test_unsupported_query_bypasses_operation_specific_constraints():
    query = ExpenseQuery(
        operation="total",
        unsupported=True,
        unsupported_reason="previsão não suportada",
    )

    assert query.unsupported is True
