"""Resolução determinística dos campos temporais de uma regra de gasto fixo.

Duas perguntas, respondidas aqui e nunca pelo LLM:

    - em que **dia do mês** a cobrança acontece (``recurrence_day``);
    - a partir de **quando** a regra vale (``starts_at``).

Este módulo deliberadamente não reusa ``calendar.resolve_occurred_at``: aquela
função recusa datas no futuro, o que é correto para um gasto já ocorrido e
errado para uma regra que pode começar no mês que vem ("minha academia começa
em outubro").

Além da resolução, o módulo responde a terceira pergunta do fluxo de
materialização: **quais meses** a regra já deveria ter gerado e ainda não gerou
(``pending_periods``). Essa parte é pura de propósito — recebe ``today`` por
parâmetro e não toca no banco — para que a elegibilidade seja testável sem
infraestrutura.
"""

import re
import unicodedata
from calendar import monthrange
from collections.abc import Iterator, Set
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime

__all__ = [
    "MAX_RETROACTIVE_PERIODS",
    "PendingPeriods",
    "RecurrenceResolutionError",
    "effective_date",
    "period_of",
    "pending_periods",
    "resolve_recurrence_day",
    "resolve_starts_at",
]

# Teto de geração retroativa por regra, por execução. Uma regra com
# ``starts_at`` muito antigo geraria dezenas de inserções em uma única
# mensagem, estourando o SLA de resposta do PRD. Como o catch-up roda a cada
# mensagem, o que sobra é gerado na seguinte.
MAX_RETROACTIVE_PERIODS = 12

_FIRST_DAY_OF_MONTH = 1
_LAST_POSSIBLE_DAY_OF_MONTH = 31
_DECEMBER = 12

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


@dataclass(frozen=True, slots=True)
class PendingPeriods:
    """Períodos que a regra deve gerar agora, e quantos ficaram para depois.

    ``remaining`` existe porque o truncamento precisa ser observável em log
    (REQ-017) sem que o chamador refaça o cálculo de elegibilidade.
    """

    due: list[date_type]
    remaining: int


def period_of(day: date_type) -> date_type:
    """Reduz uma data ao primeiro dia do seu mês — o período de competência."""
    return day.replace(day=_FIRST_DAY_OF_MONTH)


def effective_date(recurrence_day: int, period: date_type) -> date_type:
    """Data em que a cobrança cai dentro do período, ajustada a meses curtos.

    Espelha ``clamp_recurrence_day`` do banco: dia 31 vira 28 em fevereiro
    comum, 29 em bissexto e 30 em abril.
    """
    _, last_day_of_month = monthrange(period.year, period.month)
    return period.replace(day=min(recurrence_day, last_day_of_month))


def pending_periods(
    recurrence_day: int,
    starts_at: date_type,
    ends_at: date_type | None,
    already_generated: Set[date_type],
    today: date_type,
    limit: int = MAX_RETROACTIVE_PERIODS,
) -> PendingPeriods:
    """Períodos de competência elegíveis, do mais antigo ao mais recente.

    Args:
        recurrence_day: Dia do mês gravado na regra, de 1 a 31, sem clamp.
        starts_at: Início da vigência da regra.
        ends_at: Fim da vigência, ou ``None`` quando a regra não expira.
        already_generated: Competências já materializadas, lidas do banco.
        today: Data de referência no fuso do usuário.
        limit: Máximo de períodos devolvidos nesta execução.

    Returns:
        Os períodos a gerar agora e a quantidade que excedeu o limite.
    """
    eligible = [
        period
        for period in _months_from(period_of(starts_at), period_of(today))
        if period not in already_generated
        and _is_due(effective_date(recurrence_day, period), starts_at, ends_at, today)
    ]

    return PendingPeriods(due=eligible[:limit], remaining=max(len(eligible) - limit, 0))


def _months_from(first: date_type, last: date_type) -> Iterator[date_type]:
    """Percorre o primeiro dia de cada mês, de ``first`` até ``last`` inclusive."""
    period = first
    while period <= last:
        yield period
        period = _next_month(period)


def _next_month(period: date_type) -> date_type:
    if period.month == _DECEMBER:
        return period.replace(year=period.year + 1, month=1)
    return period.replace(month=period.month + 1)


def _is_due(
    charge_date: date_type,
    starts_at: date_type,
    ends_at: date_type | None,
    today: date_type,
) -> bool:
    """Um período vence quando a cobrança já passou e está dentro da vigência.

    Cobrança no futuro é recusada por regra de produto: nenhum lançamento pode
    nascer com ``occurred_at`` posterior ao instante da geração.
    """
    if not starts_at <= charge_date <= today:
        return False
    return ends_at is None or charge_date <= ends_at
