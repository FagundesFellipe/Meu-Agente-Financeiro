"""Resolução determinística dos campos temporais de uma regra de gasto fixo.

Duas perguntas, respondidas aqui e nunca pelo LLM:

    - em que **dia do mês** a cobrança acontece (``recurrence_day``);
    - a partir de **quando** a regra vale (``starts_at``).

Este módulo deliberadamente não reusa ``calendar.resolve_occurred_at``: aquela
função recusa datas no futuro, o que é correto para um gasto já ocorrido e
errado para uma regra que pode começar no mês que vem ("minha academia começa
em outubro").
"""

import re
import unicodedata
from datetime import date as date_type
from datetime import datetime

__all__ = [
    "RecurrenceResolutionError",
    "resolve_recurrence_day",
    "resolve_starts_at",
]

_FIRST_DAY_OF_MONTH = 1
_LAST_POSSIBLE_DAY_OF_MONTH = 31

# O dia é gravado literalmente: o ajuste para meses curtos é responsabilidade
# de quem gera os lançamentos, via ``clamp_recurrence_day`` no banco.
_DAY_BY_ORDINAL_WORD: dict[str, int] = {
    "primeiro": _FIRST_DAY_OF_MONTH,
    "ultimo": _LAST_POSSIBLE_DAY_OF_MONTH,
}

_TODAY_WORDS = frozenset({"hoje", "agora"})
_DIGITS = re.compile(r"\d+")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ISO_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


class RecurrenceResolutionError(ValueError):
    """O dia de recorrência ou a data de início não pôde ser interpretado."""


def _normalize(hint: str) -> str:
    """Reduz o texto a minúsculas sem acento e com espaçamento único."""
    decomposed = unicodedata.normalize("NFKD", hint)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.strip().lower())


def _single_day_number(text: str, hint: str) -> int:
    numbers = _DIGITS.findall(text)
    if len(numbers) != 1:
        raise RecurrenceResolutionError(
            f"Não foi possível identificar um único dia em {hint!r}"
        )
    return int(numbers[0])


def resolve_recurrence_day(day_hint: str | None, reference: datetime) -> int:
    """Converte o dia de cobrança informado pelo usuário em um inteiro de 1 a 31.

    Args:
        day_hint: Dia como texto ("10", "todo dia 5", "hoje"). ``None`` quando o
            usuário não informou.
        reference: "Agora" no fuso do usuário, usado por hints relativos.

    Returns:
        O dia do mês, entre 1 e 31, gravado sem clamp.

    Raises:
        RecurrenceResolutionError: Quando o dia está ausente, é ambíguo ou está
            fora do intervalo. O chamador deve transformar isso em pendência.
    """
    if not day_hint or not day_hint.strip():
        raise RecurrenceResolutionError("Dia de recorrência não informado")

    text = _normalize(day_hint)

    if text in _TODAY_WORDS:
        return reference.day

    day = next(
        (
            day_number
            for word, day_number in _DAY_BY_ORDINAL_WORD.items()
            if re.search(rf"\b{word}\b", text)
        ),
        None,
    )
    if day is None:
        day = _single_day_number(text, day_hint)

    if not _FIRST_DAY_OF_MONTH <= day <= _LAST_POSSIBLE_DAY_OF_MONTH:
        raise RecurrenceResolutionError(
            f"Dia de recorrência fora do intervalo 1-31: {day_hint!r}"
        )

    return day


def resolve_starts_at(start_hint: str | None, reference: datetime) -> date_type:
    """Resolve a partir de quando a regra passa a valer, no fuso do usuário.

    Datas no futuro são aceitas de propósito: cadastrar hoje uma mensalidade que
    começa em outubro é uma entrada legítima, e quem gera os lançamentos ignora
    os períodos anteriores a ``starts_at``.

    Args:
        start_hint: Data em ``YYYY-MM-DD``, ``YYYY-MM`` (primeiro dia do mês) ou
            "hoje". ``None`` quando o usuário não informou.
        reference: "Agora" no fuso do usuário.

    Returns:
        A data de início. Sem hint, a data de hoje no fuso do usuário.

    Raises:
        RecurrenceResolutionError: Quando o hint existe mas não é interpretável.
    """
    if not start_hint or not start_hint.strip():
        return reference.date()

    text = _normalize(start_hint)

    if text in _TODAY_WORDS:
        return reference.date()

    iso_date = _ISO_DATE.match(text)
    if iso_date:
        year, month, day = (int(group) for group in iso_date.groups())
        return _build_date(year, month, day, hint=start_hint)

    iso_month = _ISO_MONTH.match(text)
    if iso_month:
        year, month = (int(group) for group in iso_month.groups())
        return _build_date(year, month, _FIRST_DAY_OF_MONTH, hint=start_hint)

    raise RecurrenceResolutionError(
        f"Não foi possível interpretar a data de início: {start_hint!r}"
    )


def _build_date(year: int, month: int, day: int, hint: str) -> date_type:
    try:
        return date_type(year, month, day)
    except ValueError as exc:
        raise RecurrenceResolutionError(f"Data de início inválida: {hint!r}") from exc
