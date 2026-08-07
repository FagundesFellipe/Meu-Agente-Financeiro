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

import os
import sys
from pathlib import Path

import psycopg
import structlog
from dotenv import load_dotenv

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


def run_migrations(database_url: str) -> None:
    """Aplica migrações SQL pendentes ao banco de dados.

    Cria a tabela migrations se não existir, depois aplica cada arquivo
    SQL que ainda não foi registrado, em ordem alfabética.

    Args:
        database_url: Connection string do PostgreSQL.
    """
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            # Garante que a tabela de controle existe
            cur.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id          SERIAL PRIMARY KEY,
                    name        TEXT NOT NULL UNIQUE,
                    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            conn.commit()

            cur.execute("SELECT name FROM migrations ORDER BY name")
            applied = {row[0] for row in cur.fetchall()}

            # Lê e aplica migrações pendentes em ordem
            sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

            for sql_file in sql_files:
                if sql_file.name in applied:
                    logger.debug("migration_aplicada", migration=sql_file.name)
                    continue

                logger.info("aplicando_migração", migration=sql_file.name)
                sql = sql_file.read_text(encoding="utf-8")

                # Cada arquivo de migração é executado em uma transação
                # atômica: se qualquer statement falhar, nada do arquivo
                # é aplicado, e o registro em migrations também não.
                cur.execute("BEGIN")
                try:
                    cur.execute(sql)

                    cur.execute(
                        "INSERT INTO migrations (name) VALUES (%s)",
                        (sql_file.name,),
                    )
                    cur.execute("COMMIT")
                    logger.info("migração_aplicada", migration=sql_file.name)
                except Exception:
                    cur.execute("ROLLBACK")
                    raise


def main() -> None:
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
        run_migrations(database_url)
        logger.info("Migrações concluídas.")
    except psycopg.Error as e:
        logger.error(f"Erro ao aplicar migrações: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
