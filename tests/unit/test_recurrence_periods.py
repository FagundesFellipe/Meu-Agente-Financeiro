"""Testes da elegibilidade de períodos de uma regra de gasto fixo.

Puros por construção: ``pending_periods`` recebe ``today`` por parâmetro e não
toca no banco, então cada regra de elegibilidade do spec vira um caso isolado
sem infraestrutura.

Rodar só estes:
    uv run pytest tests/unit/test_recurrence_periods.py
"""

from datetime import date

import pytest

from financial_agent.agent.tools.recurrence import (
    MAX_RETROACTIVE_PERIODS,
    effective_date,
    pending_periods,
    period_of,
)

NOTHING_GENERATED: frozenset[date] = frozenset()


def _due(
    recurrence_day: int = 10,
    starts_at: date = date(2026, 9, 1),
    ends_at: date | None = None,
    already_generated: frozenset[date] = NOTHING_GENERATED,
    today: date = date(2026, 9, 15),
) -> list[date]:
    return pending_periods(
        recurrence_day=recurrence_day,
        starts_at=starts_at,
        ends_at=ends_at,
        already_generated=already_generated,
        today=today,
    ).due


def test_first_period_of_the_current_month_is_due():  # TC-001
    assert _due() == [date(2026, 9, 1)]


def test_an_already_generated_period_is_never_repeated():  # TC-002
    assert _due(already_generated=frozenset({date(2026, 9, 1)})) == []


def test_a_charge_day_that_has_not_arrived_yet_is_not_due():  # TC-003
    assert _due(today=date(2026, 9, 3)) == []


@pytest.mark.parametrize(
    ("period", "expected_day"),
    [
        (date(2026, 2, 1), 28),  # TC-004 fevereiro comum
        (date(2028, 2, 1), 29),  # TC-005 fevereiro bissexto
        (date(2026, 4, 1), 30),  # TC-006 abril
        (date(2026, 1, 1), 31),  # mês longo mantém o dia literal
    ],
)
def test_day_31_is_clamped_to_the_last_day_of_the_month(period, expected_day):
    assert effective_date(31, period) == period.replace(day=expected_day)


def test_five_missing_months_are_returned_oldest_first():  # TC-007
    due = _due(starts_at=date(2026, 5, 1), today=date(2026, 9, 15))

    assert due == [
        date(2026, 5, 1),
        date(2026, 6, 1),
        date(2026, 7, 1),
        date(2026, 8, 1),
        date(2026, 9, 1),
    ]


def test_a_long_backlog_is_truncated_at_the_retroactive_limit():  # TC-008
    result = pending_periods(
        recurrence_day=10,
        starts_at=date(2024, 9, 1),
        ends_at=None,
        already_generated=NOTHING_GENERATED,
        today=date(2026, 9, 15),
    )

    assert len(result.due) == MAX_RETROACTIVE_PERIODS
    assert result.due[0] == date(2024, 9, 1)
    assert result.due[-1] == date(2025, 8, 1)
    assert result.remaining == 13


def test_the_next_run_continues_where_the_truncation_stopped():  # TC-009
    first = pending_periods(
        recurrence_day=10,
        starts_at=date(2024, 9, 1),
        ends_at=None,
        already_generated=NOTHING_GENERATED,
        today=date(2026, 9, 15),
    )

    second = pending_periods(
        recurrence_day=10,
        starts_at=date(2024, 9, 1),
        ends_at=None,
        already_generated=frozenset(first.due),
        today=date(2026, 9, 15),
    )

    assert second.due[0] == date(2025, 9, 1)
    assert second.remaining == 1


def test_a_rule_that_already_ended_generates_nothing_after_its_end():  # TC-011
    assert _due(ends_at=date(2026, 8, 31)) == []


def test_a_rule_starting_in_the_future_generates_nothing():  # TC-012
    assert _due(starts_at=date(2026, 12, 1)) == []


def test_a_start_date_after_the_charge_day_skips_the_first_month():  # TC-013
    due = _due(recurrence_day=5, starts_at=date(2026, 9, 20), today=date(2026, 10, 15))

    assert due == [date(2026, 10, 1)]


def test_the_period_is_always_the_first_day_of_the_month():
    assert period_of(date(2026, 9, 15)) == date(2026, 9, 1)


def test_no_due_period_is_ever_charged_in_the_future():  # AC-017
    today = date(2026, 9, 15)

    due = _due(recurrence_day=31, starts_at=date(2026, 1, 1), today=today)

    assert all(effective_date(31, period) <= today for period in due)


def test_the_year_boundary_is_crossed_without_gaps():
    due = _due(recurrence_day=1, starts_at=date(2025, 11, 1), today=date(2026, 2, 5))

    assert due == [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]
