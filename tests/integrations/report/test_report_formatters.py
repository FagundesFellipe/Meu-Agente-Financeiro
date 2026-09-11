"""Formatação segura para o payload do relator."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from financial_agent.agent.report.format import format_brl, format_day, format_day_long

ZONE = ZoneInfo("America/Sao_Paulo")


def test_formats_brl_without_float():
    assert format_brl(Decimal("1234.56")) == "R$ 1.234,56"
    assert format_brl(Decimal("0")) == "R$ 0,00"


def test_formats_short_and_relative_days():
    now = datetime(2026, 8, 5, 14, 20, tzinfo=ZONE)

    assert format_day(now) == "05/08"
    assert format_day_long(now.replace(hour=12, minute=40), now) == "hoje, 12:40"
    assert (
        format_day_long(now.replace(day=4, hour=18, minute=10), now) == "ontem, 18:10"
    )
    assert format_day_long(now.replace(day=3), now) == "03/08"
