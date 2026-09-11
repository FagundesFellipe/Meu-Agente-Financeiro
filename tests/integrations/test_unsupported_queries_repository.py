"""Integração do registro RF-019."""

from uuid import uuid4

import psycopg
import pytest
import pytest_asyncio

from shared.config import settings
from shared.db import close_pool, connection
from shared.repositories.unsupported_queries import insert_unsupported_query

pytestmark = pytest.mark.db


async def _database_is_available() -> bool:
    try:
        conn = await psycopg.AsyncConnection.connect(
            settings.database_url, connect_timeout=3
        )
    except Exception:
        return False
    await conn.close()
    return True


@pytest_asyncio.fixture(autouse=True)
async def require_database():
    if not await _database_is_available():
        pytest.skip("Postgres indisponível; verifique DATABASE_URL.")
    yield
    await close_pool()


async def test_records_the_unsupported_query_fields():
    suffix = uuid4().hex[:10]
    async with connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO "user" (channel, external_user_id, name, timezone)
            VALUES ('telegram', %s, 'RF-019', 'America/Sao_Paulo')
            RETURNING id
            """,
            (f"unsupported-{suffix}",),
        )
        user_id = (await cur.fetchone())["id"]
    try:
        await insert_unsupported_query(
            user_id,
            raw_question="quanto vou gastar?",
            intent="view_expenses_report",
            normalized_question="quanto vou gastar",
            reason="previsão",
        )
        async with connection() as conn:
            cur = await conn.execute(
                """
                SELECT raw_question, intent, normalized_question, reason
                FROM unsupported_report_query
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = await cur.fetchone()
        assert row == {
            "raw_question": "quanto vou gastar?",
            "intent": "view_expenses_report",
            "normalized_question": "quanto vou gastar",
            "reason": "previsão",
        }
    finally:
        async with connection() as conn:
            await conn.execute(
                "DELETE FROM unsupported_report_query WHERE user_id = %s", (user_id,)
            )
            await conn.execute('DELETE FROM "user" WHERE id = %s', (user_id,))
