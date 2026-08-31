"""Testes das tools determinísticas de recorrência (sem rede e sem banco)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from financial_agent.agent.tools.recurrence import (
    RecurrenceResolutionError,
    resolve_recurrence_day,
    resolve_starts_at,
)

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 8, 31, 14, 20, tzinfo=TZ)


@pytest.mark.parametrize(
    ("day_hint", "expected"),
    [
        ("10", 10),
        ("dia 5", 5),
        ("todo dia 5", 5),
        (" TODO DIA 15 ", 15),
        ("no dia 1", 1),
        ("31", 31),
        ("todo dia primeiro", 1),
        ("último dia do mês", 31),
        ("hoje", 31),
    ],
)
def test_resolve_recurrence_day_reads_the_day_the_user_said(day_hint, expected):
    assert resolve_recurrence_day(day_hint, NOW) == expected


@pytest.mark.parametrize(
    "day_hint",
    [None, "", "   ", "0", "32", "99", "dia 5 ou 10", "todo mês", "2026-10-01"],
)
def test_resolve_recurrence_day_refuses_what_it_cannot_read(day_hint):
    with pytest.raises(RecurrenceResolutionError):
        resolve_recurrence_day(day_hint, NOW)


def test_recurrence_day_31_is_kept_literally():  # TC-018
    """O clamp para meses curtos é da Stack 2, via clamp_recurrence_day."""
    assert resolve_recurrence_day("todo dia 31", NOW) == 31


def test_starts_at_defaults_to_today_in_the_user_timezone():  # TC-016
    assert resolve_starts_at(None, NOW) == date(2026, 8, 31)
    assert resolve_starts_at("  ", NOW) == date(2026, 8, 31)
    assert resolve_starts_at("hoje", NOW) == date(2026, 8, 31)


def test_starts_at_accepts_a_future_date():  # TC-015
    """Contraste com resolve_occurred_at, que levantaria DateResolutionError."""
    assert resolve_starts_at("2026-10-01", NOW) == date(2026, 10, 1)


def test_starts_at_accepts_a_month_and_uses_its_first_day():
    assert resolve_starts_at("2026-10", NOW) == date(2026, 10, 1)


def test_starts_at_accepts_a_past_date():
    assert resolve_starts_at("2026-01-15", NOW) == date(2026, 1, 15)


@pytest.mark.parametrize(
    "start_hint", ["2026-02-30", "2026-13-01", "outubro", "amanhã"]
)
def test_starts_at_refuses_what_it_cannot_read(start_hint):
    with pytest.raises(RecurrenceResolutionError):
        resolve_starts_at(start_hint, NOW)
