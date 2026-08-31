"""Resolução/Normalização determinística da categoria de um gasto.

A escolha semântica é do LLM (``ExtractedExpense.category_hint``), mas a
conversão para uma categoria **que existe no banco** é feita aqui. Isso evita
que o modelo invente uma categoria e quebre a FK ``expense.category_id``.

Ordem de resolução:
    1. nome exato do hint;
    2. nome normalizado do hint (sem acento/caixa);
    3. correspondência aproximada do hint (erro de digitação do modelo);
    4. palavra-chave da descrição do gasto batendo com nome de categoria;
    5. fallback configurável (``settings.fallback_category_name``).
"""

import re
import unicodedata
from difflib import get_close_matches

from shared.config import settings
from shared.repositories.categories import CategoryRecord

__all__ = [
    "CategoryResolutionError",
    "find_category",
    "normalize",
    "resolve_category",
]


class CategoryResolutionError(ValueError):
    """Nenhuma categoria pôde ser resolvida — nem o fallback existe."""


def normalize(text: str) -> str:
    """Reduz o texto a minúsculas sem acento, para comparação estável."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.strip().lower())


def _by_exact_name(
    hint: str, categories: list[CategoryRecord]
) -> CategoryRecord | None:
    return next((c for c in categories if c.name == hint), None)


def _by_normalized(
    hint: str, categories: list[CategoryRecord]
) -> CategoryRecord | None:
    target = normalize(hint)
    return next(
        (
            c
            for c in categories
            if normalize(c.name) == target or normalize(c.normalized_name) == target
        ),
        None,
    )


def _by_fuzzy(hint: str, categories: list[CategoryRecord]) -> CategoryRecord | None:
    index = {normalize(c.name): c for c in categories}
    matches = get_close_matches(normalize(hint), list(index), n=1, cutoff=0.80)
    return index[matches[0]] if matches else None


def _by_description(
    description: str, categories: list[CategoryRecord]
) -> CategoryRecord | None:
    """Último recurso antes do fallback: a descrição cita o nome da categoria."""
    text = normalize(description)
    for category in categories:
        name = normalize(category.name)
        if re.search(rf"\b{re.escape(name)}\b", text):
            return category
    return None


def find_category(
    description: str,
    hint: str | None,
    categories: list[CategoryRecord],
) -> CategoryRecord | None:
    """Procura a categoria do gasto sem jamais recorrer ao fallback genérico.

    É a cadeia de estratégias 1 a 4 do módulo. Fluxos em que uma categoria
    genérica atribuída automaticamente corromperia o dado — gasto recorrente,
    por exemplo — usam esta função e transformam o ``None`` em uma pergunta ao
    usuário, em vez de gravar um palpite.
    """
    if hint:
        for strategy in (_by_exact_name, _by_normalized, _by_fuzzy):
            match = strategy(hint, categories)
            if match is not None:
                return match

    return _by_description(description, categories)


def resolve_category(
    description: str,
    hint: str | None,
    categories: list[CategoryRecord],
) -> CategoryRecord:
    """Escolhe a categoria do gasto entre as disponíveis para o usuário.

    Args:
        description: Descrição do gasto extraída pelo LLM.
        hint: Nome de categoria sugerido pelo LLM (pode ser ``None``).
        categories: Categorias disponíveis (globais + pessoais).

    Returns:
        A categoria escolhida, sempre pertencente a ``categories``.

    Raises:
        CategoryResolutionError: Se ``categories`` estiver vazia ou não contiver
            a categoria de fallback.
    """
    if not categories:
        raise CategoryResolutionError("Nenhuma categoria disponível para o usuário")

    match = find_category(description, hint, categories)
    if match is not None:
        return match

    fallback = _by_normalized(settings.fallback_category_name, categories)
    if fallback is None:
        raise CategoryResolutionError(
            f"Categoria de fallback {settings.fallback_category_name!r} "
            "não existe entre as categorias do usuário"
        )

    return fallback
