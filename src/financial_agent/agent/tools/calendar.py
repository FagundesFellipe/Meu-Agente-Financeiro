"""Tools para lidar e tratar ações que envolvem datas.

O prompt pede que o LLM já devolva ``date_hint`` em ISO (``YYYY-MM-DD``),
calculado a partir da data atual injetada no contexto. Este módulo:

    1. valida esse ISO;
    2. serve de rede de segurança para expressões relativas em português,
       caso o modelo devolva "ontem" em vez da data resolvida;
    3. aplica a regra de negócio de que **data futura não é aceita**.
"""

import re
from datetime import date as date_type
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.config import settings

__all__ = ["DateResolutionError", "resolve_occurred_at", "user_now"]


class DateResolutionError(ValueError):
    """A data informada é inválida ou está no futuro."""


_ACCENTS = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüç", "aaaaaeeeeiiiiooooouuuuc")

_RELATIVE_DAYS: dict[str, int] = {
    "hoje": 0,
    "agora": 0,
    "ontem": -1,
    "anti ontem": -2,
    "ante ontem": -2,
    "anteontem": -2,
    "antes de ontem": -2,
    "antiontem": -2,
}

_MONTHS: dict[str, int] = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DAY_ONLY = re.compile(r"^dia\s+(\d{1,2})$")
_DAY_MONTH = re.compile(r"^(?:dia\s+)?(\d{1,2})\s+de\s+([a-z]+)$")
_DAY_MONTH_NUMERIC = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")
_TIME = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(?:h(?:oras?)?)?$")


def _zone(timezone: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(timezone or settings.default_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(settings.default_timezone)


def user_now(timezone: str | None = None) -> datetime:
    """Data e hora atuais no fuso do usuário."""
    return datetime.now(tz=_zone(timezone))


def _resolve_date(hint: str, reference: datetime) -> date_type:
    text = re.sub(r"\s+", " ", hint.strip().lower().translate(_ACCENTS))
    today = reference.date()

    if text in _RELATIVE_DAYS:
        return today + timedelta(days=_RELATIVE_DAYS[text])

    iso = _ISO_DATE.match(text)
    if iso:
        year, month, day = (int(g) for g in iso.groups())
        try:
            return date_type(year, month, day)
        except ValueError as exc:
            raise DateResolutionError(f"Data inválida: {hint!r}") from exc

    day_only = _DAY_ONLY.match(text)
    if day_only:
        return _day_in_nearest_month(int(day_only.group(1)), today, hint)

    day_month = _DAY_MONTH.match(text)
    if day_month:
        day, month_name = day_month.groups()
        month = _MONTHS.get(month_name)
        if month is None:
            raise DateResolutionError(f"Mês desconhecido em {hint!r}")
        return _with_nearest_year(int(day), month, today, hint)

    numeric = _DAY_MONTH_NUMERIC.match(text)
    if numeric:
        day, month, year = numeric.groups()
        if year is None:
            return _with_nearest_year(int(day), int(month), today, hint)
        full_year = int(year) if len(year) == 4 else 2000 + int(year)
        try:
            return date_type(full_year, int(month), int(day))
        except ValueError as exc:
            raise DateResolutionError(f"Data inválida: {hint!r}") from exc

    raise DateResolutionError(f"Não foi possível interpretar a data: {hint!r}")


def _day_in_nearest_month(day: int, today: date_type, hint: str) -> date_type:
    """'dia 15' = dia 15 deste mês; se ainda não chegou, o do mês passado."""
    try:
        candidate = today.replace(day=day)
    except ValueError as exc:
        raise DateResolutionError(f"Dia inválido em {hint!r}") from exc

    if candidate > today:
        previous_month_end = today.replace(day=1) - timedelta(days=1)
        try:
            candidate = previous_month_end.replace(day=day)
        except ValueError as exc:
            raise DateResolutionError(f"Dia inválido em {hint!r}") from exc

    return candidate


def _with_nearest_year(day: int, month: int, today: date_type, hint: str) -> date_type:
    """Resolve a data no ano atual; datas futuras são inválidas."""
    try:
        candidate = date_type(today.year, month, day)
    except ValueError as e:
        raise DateResolutionError(f"Data inválida: {hint!r}") from e

    if candidate > today:
        raise DateResolutionError(f"Data futura não permitida: {hint!r}")

    return candidate


def _resolve_time(hint: str) -> time:
    text = hint.strip().lower().translate(_ACCENTS)
    match = _TIME.match(text)
    if not match:
        raise DateResolutionError(f"Não foi possível interpretar o horário: {hint!r}")

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise DateResolutionError(f"Horário fora do intervalo: {hint!r}")

    return time(hour, minute)


def resolve_occurred_at(
    date_hint: str | None,
    time_hint: str | None = None,
    timezone: str | None = None,
    reference: datetime | None = None,
) -> datetime:
    """Resolve quando o gasto ocorreu, no fuso do usuário.

    Args:
        date_hint: Data em ISO ou expressão relativa. ``None`` = hoje.
        time_hint: Horário em ``HH:MM``. ``None`` = horário atual quando a data
            é hoje, meio-dia quando é uma data passada (evita gravar 00:00, que
            se desloca de dia ao converter fuso).
        timezone: Fuso do usuário (IANA). Default: ``settings.default_timezone``.
        reference: "Agora" — injetável nos testes.

    Returns:
        ``datetime`` com timezone.

    Raises:
        DateResolutionError: Data ilegível ou no futuro.
    """
    zone = _zone(timezone)
    now = reference.astimezone(zone) if reference else datetime.now(tz=zone)

    resolved_date = _resolve_date(date_hint, now) if date_hint else now.date()

    if time_hint:
        resolved_time = _resolve_time(time_hint)
    elif resolved_date == now.date():
        resolved_time = now.time().replace(microsecond=0)
    else:
        resolved_time = time(12, 0)

    occurred_at = datetime.combine(resolved_date, resolved_time, tzinfo=zone)

    if occurred_at > now:
        raise DateResolutionError(
            f"Data no futuro não é aceita: {occurred_at.isoformat()}"
        )

    return occurred_at
