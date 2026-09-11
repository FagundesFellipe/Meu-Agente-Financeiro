"""Sugestões de categoria sem fallback nem categoria pessoal."""

from uuid import uuid4

from financial_agent.agent.tools.get_category import suggest_similar_categories
from shared.repositories.categories import CategoryRecord


def category(name: str, *, personal: bool = False) -> CategoryRecord:
    return CategoryRecord(
        id=uuid4(),
        name=name,
        normalized_name=name.casefold(),
        description=None,
        is_personal=personal,
    )


def test_suggests_only_similar_global_categories():
    categories = [
        category("Mercado"),
        category("Transporte"),
        category("Mercadinho pessoal", personal=True),
    ]

    assert suggest_similar_categories("mercadu", categories, 3) == ["Mercado"]


def test_respects_limit_and_empty_limit():
    categories = [category("Casa"), category("Casamento")]

    assert len(suggest_similar_categories("casa", categories, 1)) == 1
    assert suggest_similar_categories("casa", categories, 0) == []
