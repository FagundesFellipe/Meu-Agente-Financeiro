"""Testes do parser de valores monetários.

O parser agora só faz validação mecânica (algarismos + `.`/`,` + > 0).
Interpretação de linguagem natural ("duzentos reais", "8 e 50", parcelamento)
é responsabilidade do LLM, não deste módulo.
"""

from decimal import Decimal

import pytest

from financial_agent.agent.tools.amount_parser import AmountParseError, parse_amount


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("35", "35.00"),
        ("R$ 120,50", "120.50"),
        ("r$120,50", "120.50"),
        ("120,50", "120.50"),
        ("12.90", "12.90"),
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("55,90", "55.90"),
        ("8,50", "8.50"),
        ("  40  ", "40.00"),
    ],
)
def test_parse_numeric_formats(raw: str, expected: str):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "0",
        "-10",
        "bastante",
        # O LLM deve normalizar estes casos — se chegar cru, o Python rejeita:
        "8 e 50",
        "duzentos reais",
        "3x de 50",
        "3 x 50",
        "30 e 40 e 50",
    ],
)
def test_rejects_ambiguous_or_invalid(raw: str):
    with pytest.raises(AmountParseError):
        parse_amount(raw)


def test_result_is_always_two_decimal_places():
    assert str(parse_amount("35")) == "35.00"
    assert str(parse_amount("7,5")) == "7.50"


def test_never_returns_float():
    assert isinstance(parse_amount("19,99"), Decimal)
