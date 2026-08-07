"""Testes da resolução de data/hora do gasto."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from financial_agent.agent.tools.calendar import (
    DateResolutionError,
    resolve_occurred_at,
)

TZ = "America/Sao_Paulo"
ZONE = ZoneInfo(TZ)
NOW = datetime(2026, 8, 3, 14, 20, 0, tzinfo=ZONE)  # segunda-feira


def resolve(date_hint, time_hint=None):
    return resolve_occurred_at(date_hint, time_hint, timezone=TZ, reference=NOW)


def test_none_hint_uses_today_and_current_time():
    occurred = resolve(None)

    assert occurred.date() == NOW.date()
    assert occurred.hour == NOW.hour
    assert occurred.tzinfo is not None


@pytest.mark.parametrize(
    ("hint", "expected_day"),
    [
        ("hoje", 3),
        ("ontem", 2),
        ("anteontem", 1),
        ("Ontem", 2),
        ("ANTEONTEM", 1),
    ],
)
def test_relative_expressions(hint: str, expected_day: int):
    assert resolve(hint).day == expected_day


def test_iso_date():
    occurred = resolve("2026-07-25")

    assert (occurred.year, occurred.month, occurred.day) == (2026, 7, 25)


def test_past_date_defaults_to_noon_to_survive_timezone_conversion():
    occurred = resolve("2026-07-25")

    assert (occurred.hour, occurred.minute) == (12, 0)
    assert occurred.astimezone(ZoneInfo("UTC")).date() == occurred.date()


def test_day_only_falls_back_to_previous_month_when_still_in_the_future():
    # Hoje é 03/08; "dia 15" só pode ser 15/07.
    occurred = resolve("dia 15")

    assert (occurred.month, occurred.day) == (7, 15)


def test_day_only_uses_current_month_when_already_past():
    occurred = resolve("dia 1")

    assert (occurred.month, occurred.day) == (8, 1)


def test_day_and_month_by_name():
    occurred = resolve("25 de julho")

    assert (occurred.year, occurred.month, occurred.day) == (2026, 7, 25)


def test_day_and_month_by_name_rolls_back_a_year_when_in_the_future():
    with pytest.raises(DateResolutionError):
        resolve("25 de dezembro")


def test_numeric_day_month():
    occurred = resolve("25/07")

    assert (occurred.year, occurred.month, occurred.day) == (2026, 7, 25)


@pytest.mark.parametrize(
    ("time_hint", "expected"),
    [("19:30", (19, 30)), ("19h", (19, 0)), ("7", (7, 0)), ("07:05", (7, 5))],
)
def test_time_hints(time_hint: str, expected: tuple[int, int]):
    occurred = resolve("ontem", time_hint)

    assert (occurred.hour, occurred.minute) == expected


def test_rejects_future_date():
    with pytest.raises(DateResolutionError):
        resolve("2026-08-04")


def test_rejects_future_time_today():
    with pytest.raises(DateResolutionError):
        resolve("hoje", "23:00")


@pytest.mark.parametrize("hint", ["semana passada", "2026-13-01", "dia 32", "qualquer"])
def test_rejects_unparseable(hint: str):
    with pytest.raises(DateResolutionError):
        resolve(hint)


def test_invalid_timezone_falls_back_to_default():
    occurred = resolve_occurred_at("ontem", timezone="Nao/Existe", reference=NOW)

    assert occurred.day == 2
