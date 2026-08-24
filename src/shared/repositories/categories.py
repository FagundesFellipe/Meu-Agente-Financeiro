"""Consultas à tabela ``category``.

As categorias globais (``user_id IS NULL``) são visíveis a todos os usuários;
as pessoais só ao dono. A política de SELECT em 003_triggers_and_rls.sql já
garante isso — a query abaixo repete o filtro por defesa em profundidade.
"""

from dataclasses import dataclass
from uuid import UUID

from shared.db import user_connection


@dataclass(frozen=True, slots=True)
class CategoryRecord:
    """Categoria existente no banco, com o id necessário para gravar um gasto."""

    id: UUID
    name: str
    normalized_name: str
    description: str | None
    is_personal: bool


async def list_available_categories(user_id: str | UUID) -> list[CategoryRecord]:
    """Retorna todas as categorias que o usuário pode usar (globais + pessoais)."""

    _SELECT_AVAILABLE = """
    SELECT id, user_id, name, normalized_name, description, is_default
    FROM category
    WHERE is_active IS TRUE
      AND (user_id IS NULL OR user_id = %(user_id)s)
    ORDER BY user_id NULLS LAST, name
"""

    async with user_connection(str(user_id)) as conn:
        cur = await conn.execute(_SELECT_AVAILABLE, {"user_id": str(user_id)})
        rows = await cur.fetchall()

    return [
        CategoryRecord(
            id=row["id"],
            name=row["name"],
            normalized_name=row["normalized_name"],
            description=row["description"],
            is_personal=row["user_id"] is not None,
        )
        for row in rows
    ]


def format_categories_for_prompt(categories: list[CategoryRecord]) -> str:
    """Formata a lista de categorias para injeção no contexto do LLM."""
    return "\n".join(
        f"- {c.name}: {c.description}" if c.description else f"- {c.name}"
        for c in categories
    )
