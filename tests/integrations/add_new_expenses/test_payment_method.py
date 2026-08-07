"""Testes da normalização do meio de pagamento para o CHECK da tabela expense."""

import pytest

from financial_agent.agent.tools.payment_method import normalize_payment_method

# Valores aceitos pelo CHECK em db/migrations/002_expenses.sql
ALLOWED = {"pix", "credit_card", "debit_card", "cash", "not_informed"}


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        ("pix", "pix"),
        ("PIX", "pix"),
        ("transferência", "pix"),
        ("credit_card", "credit_card"),
        ("crédito", "credit_card"),
        ("Cartão de Crédito", "credit_card"),
        ("no crédito", "credit_card"),
        ("parcelado", "credit_card"),
        ("débito", "debit_card"),
        ("cartão de débito", "debit_card"),
        ("dinheiro", "cash"),
        ("espécie", "cash"),
        ("à vista", "cash"),
    ],
)
def test_normalizes_known_variations(hint: str, expected: str):
    assert normalize_payment_method(hint) == expected


@pytest.mark.parametrize("hint", [None, "", "   ", "boleto", "criptomoeda", "vale"])
def test_unknown_never_raises_and_falls_back(hint):
    assert normalize_payment_method(hint) == "not_informed"


def test_output_is_always_accepted_by_the_check_constraint():
    samples = ["pix", "crédito", "débito", "dinheiro", None, "outro qualquer"]

    assert {normalize_payment_method(s) for s in samples} <= ALLOWED
