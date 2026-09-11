"""Resolução de períodos fechados do RF-017."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from financial_agent.agent.tools.period import PeriodResolutionError, resolve_period

ZONE = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 8, 5, 14, 20, tzinfo=ZONE)  # quarta-feira


@pytest.mark.parametrize(
    ("symbol", "start", "end", "label", "unit"),
    [
        ("today", (2026, 8, 5), (2026, 8, 6), "hoje", "day"),
        ("yesterday", (2026, 8, 4), (2026, 8, 5), "ontem", "day"),
        ("this_week", (2026, 8, 3), (2026, 8, 10), "esta semana", "week"),
        ("last_week", (2026, 7, 27), (2026, 8, 3), "semana passada", "week"),
        ("this_month", (2026, 8, 1), (2026, 9, 1), "este mês", "month"),
        ("last_month", (2026, 7, 1), (2026, 8, 1), "mês passado", "month"),
    ],
)
def test_resolves_symbolic_periods(symbol, start, end, label, unit):
    period = resolve_period(symbol, reference=NOW)

    assert (period.start.year, period.start.month, period.start.day) == start
    assert (period.end.year, period.end.month, period.end.day) == end
    assert period.label == label
    assert period.unit == unit
    assert period.start.tzinfo is not None
    assert period.end.tzinfo is not None


def test_resolves_specific_day_with_readable_label():
    period = resolve_period("specific_day", day_hint="22/07", reference=NOW)

    assert period.label == "22/07"
    assert period.start.day == 22
    assert period.end.day == 23


def test_rejects_invalid_or_future_specific_day():
    with pytest.raises(PeriodResolutionError):
        resolve_period("specific_day", day_hint="inexistente", reference=NOW)
    with pytest.raises(PeriodResolutionError):
        resolve_period("specific_day", day_hint="2026-08-06", reference=NOW)
