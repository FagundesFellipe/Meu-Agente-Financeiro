"""Testes da resolução determinística de categoria."""

from uuid import uuid4

import pytest

from financial_agent.agent.tools.get_category import (
    CategoryResolutionError,
    resolve_category,
)
from shared.repositories.categories import CategoryRecord


def make_category(name: str, normalized: str, personal: bool = False):
    return CategoryRecord(
        id=uuid4(),
        name=name,
        normalized_name=normalized,
        description=f"descrição de {name}",
        is_personal=personal,
    )


@pytest.fixture
def categories():
    return [
        make_category("Alimentação", "alimentacao"),
        make_category("Transporte", "transporte"),
        make_category("Saúde e bem-estar", "saude_e_bem-estar"),
        make_category("Outros gastos", "outros_gastos"),
        make_category("Padel", "padel", personal=True),
    ]


def test_exact_name(categories):
    assert resolve_category("almoço", "Alimentação", categories).name == "Alimentação"


def test_accent_and_case_insensitive(categories):
    assert resolve_category("almoço", "alimentacao", categories).name == "Alimentação"
    assert resolve_category("almoço", "ALIMENTAÇÃO", categories).name == "Alimentação"


def test_matches_by_normalized_name(categories):
    resolved = resolve_category("consulta", "saude_e_bem-estar", categories)

    assert resolved.name == "Saúde e bem-estar"


def test_tolerates_model_typo(categories):
    assert resolve_category("uber", "Transportes", categories).name == "Transporte"


def test_personal_category_is_selectable(categories):
    resolved = resolve_category("aula", "Padel", categories)

    assert resolved.name == "Padel"
    assert resolved.is_personal is True


def test_hallucinated_category_falls_back_instead_of_breaking_the_fk(categories):
    resolved = resolve_category("algo aleatório", "Criptomoedas", categories)

    assert resolved.name == "Outros gastos"
    assert resolved in categories


def test_no_hint_uses_description_keyword(categories):
    assert resolve_category("transporte para o aeroporto", None, categories).name == (
        "Transporte"
    )


def test_no_hint_and_no_keyword_falls_back(categories):
    assert resolve_category("xyz", None, categories).name == "Outros gastos"


def test_empty_category_list_raises(categories):
    with pytest.raises(CategoryResolutionError):
        resolve_category("almoço", "Alimentação", [])


def test_missing_fallback_category_raises():
    only_food = [make_category("Alimentação", "alimentacao")]

    with pytest.raises(CategoryResolutionError):
        resolve_category("xyz", None, only_food)


def test_always_returns_a_category_from_the_given_list(categories):
    for hint in ["Alimentação", "inexistente", None, "transporte"]:
        assert resolve_category("qualquer coisa", hint, categories) in categories
