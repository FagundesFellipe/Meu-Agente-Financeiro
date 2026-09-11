"""Resolução determinística de símbolos de período para intervalos SQL."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Literal

from financial_agent.agent.state_graph import PeriodSymbol
from financial_agent.agent.tools.calendar import (
    DateResolutionError,
    _zone,
    resolve_calendar_date,
)

WEEK_START = 0


class PeriodResolutionError(ValueError):
    """O símbolo ou a data específica não formam um período válido."""


@dataclass(frozen=True, slots=True)
class ResolvedPeriod:
    label: str
    unit: Literal["day", "week", "month"]
    start: datetime
    end: datetime


def _at_midnight(value, zone):
    return datetime.combine(value, time.min, tzinfo=zone)


def _next_month_start(current: datetime) -> datetime:
    if current.month == 12:
        return current.replace(year=current.year + 1, month=1, day=1)
    return current.replace(month=current.month + 1, day=1)


def resolve_period(
    symbol: PeriodSymbol,
    *,
    day_hint: str | None = None,
    timezone: str | None = None,
    reference: datetime | None = None,
) -> ResolvedPeriod:
    """Resolve um símbolo fechado em intervalo timezone-aware ``[start, end)``."""
    zone = _zone(timezone)
    now = reference.astimezone(zone) if reference else datetime.now(tz=zone)
    today_start = _at_midnight(now.date(), zone)

    if symbol == "today":
        return ResolvedPeriod(
            "hoje", "day", today_start, today_start + timedelta(days=1)
        )
    if symbol == "yesterday":
        start = today_start - timedelta(days=1)
        return ResolvedPeriod("ontem", "day", start, today_start)
    if symbol in {"this_week", "last_week"}:
        this_week = today_start - timedelta(
            days=(today_start.weekday() - WEEK_START) % 7
        )
        start = this_week if symbol == "this_week" else this_week - timedelta(days=7)
        label = "esta semana" if symbol == "this_week" else "semana passada"
        return ResolvedPeriod(label, "week", start, start + timedelta(days=7))
    if symbol in {"this_month", "last_month"}:
        this_month = today_start.replace(day=1)
        if symbol == "this_month":
            return ResolvedPeriod(
                "este mês", "month", this_month, _next_month_start(this_month)
            )
        previous_month_end = this_month.date() - timedelta(days=1)
        start = _at_midnight(previous_month_end.replace(day=1), zone)
        return ResolvedPeriod("mês passado", "month", start, this_month)
    if symbol == "specific_day" and day_hint:
        try:
            resolved_date = resolve_calendar_date(day_hint, now)
        except DateResolutionError as exc:
            raise PeriodResolutionError(str(exc)) from exc
        if resolved_date > now.date():
            raise PeriodResolutionError("Data futura não permitida")
        start = _at_midnight(resolved_date, zone)
        return ResolvedPeriod(
            f"{resolved_date.day:02d}/{resolved_date.month:02d}",
            "day",
            start,
            start + timedelta(days=1),
        )
    raise PeriodResolutionError(f"Período inválido: {symbol!r}")
