"""Formatação determinística dos dados exibidos pelo agente relator."""

from datetime import date, datetime, timedelta
from decimal import Decimal


def format_brl(value: Decimal) -> str:
    """Formata ``Decimal`` como BRL sem conversão para ponto flutuante."""
    fixed = f"{value.quantize(Decimal('0.01')):,.2f}"
    return f"R$ {fixed.replace(',', '#').replace('.', ',').replace('#', '.')}"


def format_day(value: date | datetime) -> str:
    return value.strftime("%d/%m")


def format_day_long(value: datetime, now: datetime) -> str:
    local_value = value.astimezone(now.tzinfo)
    if local_value.date() == now.date():
        return f"hoje, {local_value:%H:%M}"
    if local_value.date() == now.date() - timedelta(days=1):
        return f"ontem, {local_value:%H:%M}"
    return format_day(local_value)
