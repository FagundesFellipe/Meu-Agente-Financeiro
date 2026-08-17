(
    """"""
    """Script standalone de migração do banco de dados.

Lê arquivos SQL de db/migrations/ e aplica os pendentes em ordem.
Controla quais migrações já foram aplicadas via tabela migrations.

Uso:
    python db/migrate.py

Requer a variável DATABASE_URL configurada (via .env ou env var).
"""
)

import asyncio
import os
import sys
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv

from src.shared.db import connection

logger = structlog.get_logger()

load_dotenv()


def _resolve_migrations_dir() -> Path:
    """Resolve o diretório de migrações para dev local e Docker"""

    candidates = [
        Path(__file__).parent / "migrations",
        Path.cwd() / "db" / "migrations",
        Path("/app/db/migrations"),
    ]

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    return candidates[0]


MIGRATIONS_DIR = _resolve_migrations_dir()


async def _ensure_migrations_table(conn) -> None:
    """Cria a tabela de controle de migrações, se ainda não existir."""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def _list_applied_migrations(conn) -> set[str]:
    """Retorna o conjunto de nomes de migrações já aplicadas."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT name FROM migrations ORDER BY name")
        rows = await cur.fetchall()
    return {row["name"] for row in rows}


async def _apply_migration(conn, sql_file: Path) -> None:
    """Aplica um único arquivo SQL e registra na tabela migrations.

    Deve ser chamado dentro de uma transação ativa.
    """
    sql = sql_file.read_text(encoding="utf-8")
    await conn.execute(sql)
    await conn.execute(
        "INSERT INTO migrations (name) VALUES (%s)",
        (sql_file.name,),
    )


async def run_migrations() -> None:
    """Aplica migrações SQL pendentes ao banco de dados.

    Cada arquivo é aplicado em uma transação independente: se uma falhar,
    as anteriores já permanecem registradas.
    """
    async with connection() as conn:
        async with conn.transaction():
            await _ensure_migrations_table(conn)

    async with connection() as conn:
        async with conn.transaction():
            applied = await _list_applied_migrations(conn)

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for sql_file in sql_files:
        if sql_file.name in applied:
            logger.debug("migration_ja_aplicada", migration=sql_file.name)
            continue

        logger.info("aplicando_migracao", migration=sql_file.name)

        try:
            async with connection() as conn:
                async with conn.transaction():
                    await _apply_migration(conn, sql_file)

        except Exception as exc:
            logger.error(
                "falha_na_migracao",
                migration=sql_file.name,
                error=str(exc),
            )
            raise

        logger.info("migracao_aplicada", migration=sql_file.name)


async def main() -> None:
    """Entry point do script de migração."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error(
            "Erro: DATABASE_URL não configurada. "
            "Configure via .env ou variável de ambiente."
        )

        sys.exit(1)

    logger.info("Conectando ao banco de dados...")
    try:
        await run_migrations()
        logger.info("Migrações concluídas.")
    except psycopg.Error as e:
        logger.error(f"Erro ao aplicar migrações: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
