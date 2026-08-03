"""Sincronização idempotente das categorias globais com o banco de dados.

Lê as categorias de shared/categories.py (fonte única da verdade) e faz
upsert na tabela category. Seguro para rodar repetidamente — categorias já
existentes não são alteradas.

Uso via Makefile:
    make sync-categories

Uso programático:
    from financial_agent.shared.db_sync_categories import sync_categories
    sync_categories(conn)
"""

import psycopg
from psycopg import Connection

from shared.categories import GLOBAL_CATEGORIES
from shared.config import settings

UPSERT_SQL = """
    INSERT INTO category
        (name, normalized_name, description, is_default, is_active)
    VALUES (
        %(name)s, %(normalized_name)s, %(description)s,
        %(is_default)s, %(is_active)s
    )
    ON CONFLICT (normalized_name) WHERE user_id IS NULL DO NOTHING
"""


def sync_categories(conn: Connection) -> int:
    """Faz upsert das categorias globais no banco.

    Args:
        conn: Conexão psycopg ativa.

    Returns:
        Número de categorias inseridas (não conta as já existentes).
    """
    inserted = 0
    with conn.cursor() as cur:
        for cat in GLOBAL_CATEGORIES:
            cur.execute(
                UPSERT_SQL,
                {
                    "name": cat.name,
                    "normalized_name": cat.normalized_name,
                    "description": cat.description,
                    "is_default": cat.is_default,
                    "is_active": cat.is_active,
                },
            )
            if cur.rowcount and cur.rowcount > 0:
                inserted += 1
        conn.commit()
    return inserted
