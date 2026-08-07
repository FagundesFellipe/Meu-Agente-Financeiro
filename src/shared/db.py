"""Acesso assíncrono ao Postgres via pool de conexões compartilhado.

Um único ``AsyncConnectionPool`` por processo é reusado por todos os
repositórios. O pool é aberto sob demanda na primeira consulta e deve ser
fechado no shutdown da aplicação (``close_pool``).

Uso:
    from shared.db import user_connection

    # Consulta já isolada por RLS
    async with user_connection(user_id) as conn:
        ...

Nota sobre RLS:
    As políticas de ``db/migrations/003_triggers_and_rls.sql`` dependem da
    variável de sessão ``app.current_user_id``. ``user_connection`` a define
    com escopo de transação (``set_config(..., is_local => true)``), de modo
    que ela nunca vaza para a próxima conexão devolvida ao pool.

    Atenção: RLS não se aplica ao dono das tabelas. Para o isolamento valer de
    fato em produção, a aplicação precisa conectar com um role sem BYPASSRLS e
    que não seja o owner (ou as tabelas precisam de FORCE ROW LEVEL SECURITY).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import structlog
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from shared.config import settings

logger = structlog.get_logger()

# Todas as conexões saem do pool com row_factory=dict_row; o alias abaixo faz o
# type checker enxergar isso, já que a configuração vai por ``kwargs``.
DictConnection = AsyncConnection[DictRow]

_pool: "AsyncConnectionPool[DictConnection] | None" = None


async def get_pool() -> "AsyncConnectionPool[DictConnection]":
    """Retorna o pool do processo, abrindo-o na primeira chamada."""
    global _pool

    if _pool is None:
        _pool = cast(
            "AsyncConnectionPool[DictConnection]",
            AsyncConnectionPool(
                conninfo=settings.database_url,
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_max_size,
                kwargs={"row_factory": dict_row},
                open=False,
            ),
        )
        await _pool.open(wait=True, timeout=settings.db_pool_open_timeout)
        db_host = settings.database_url.split("@")[-1]
        logger.info("db_pool_created", database_url=db_host)
    return _pool


async def close_pool() -> None:
    """Fecha o pool. Deve ser chamado no shutdown da API e do worker."""
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("db_pool_closed")


@asynccontextmanager
async def user_connection(user_id: str) -> AsyncGenerator[DictConnection]:
    """Conexão com ``app.current_user_id`` definido para a transação.

    Todas as consultas a tabelas financeiras devem passar por aqui — é o que
    ativa o isolamento por usuário exigido pelo PRD (RNF-004).
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_user_id', %s, true)",
                (str(user_id),),
            )
            yield conn


@asynccontextmanager
async def connection() -> AsyncGenerator[DictConnection]:
    """Conexão sem usuário definido (para operações não-financeiras).

    Use apenas para lookups que acontecem antes da identificação do usuário
    (ex.: resolução de canal, health checks internos). Para qualquer acesso a
    tabelas financeiras, prefira ``user_connection``.
    """
    pool = await get_pool()
    async with pool.connection() as conn:
        yield conn


async def check_db_health() -> bool:
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error("db_health_check_failed", error=str(e))
        return False
