"""Integração da ordenação da fila por ``thread_id``."""

import asyncio
from uuid import UUID, uuid4

import psycopg
import pytest
import pytest_asyncio

from shared.config import settings
from shared.db import close_pool, connection
from shared.queue import claim_next, hold_thread_processing_lock, mark_done

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
        pytest.skip(f"Postgres indisponível em {settings.database_url}")
    yield
    await close_pool()


@pytest_asyncio.fixture
async def queue_user() -> UUID:
    external_user_id = f"queue-test-{uuid4().hex[:10]}"
    async with connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO "user" (channel, external_user_id, name, timezone)
            VALUES ('telegram', %s, 'Queue Test', 'America/Sao_Paulo')
            RETURNING id
            """,
            (external_user_id,),
        )
        row = await cur.fetchone()
        assert row is not None
        user_id = row["id"]

    yield user_id

    async with connection() as conn:
        await conn.execute("DELETE FROM message_queue WHERE user_id = %s", (user_id,))
        await conn.execute('DELETE FROM "user" WHERE id = %s', (user_id,))


async def _enqueue_message(user_id: UUID, thread_id: str, content: str) -> UUID:
    async with connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO message_queue
                (user_id, phone_number, channel, agent_id, thread_id, incoming_message)
            VALUES (%s, %s, 'telegram', 'financial-agent', %s, %s)
            RETURNING id
            """,
            (user_id, thread_id, thread_id, content),
        )
        row = await cur.fetchone()
        assert row is not None
        return row["id"]


async def test_two_workers_claim_different_threads_before_the_same_thread(
    queue_user: UUID,
):
    first_thread = f"thread-a-{uuid4().hex}"
    second_thread = f"thread-b-{uuid4().hex}"
    first_message = await _enqueue_message(queue_user, first_thread, "primeira")
    await _enqueue_message(queue_user, first_thread, "segunda")
    await _enqueue_message(queue_user, second_thread, "outra conversa")

    claimed = await asyncio.gather(claim_next(), claim_next())
    claimed_messages = [message for message in claimed if message is not None]

    assert len(claimed_messages) == 2
    assert {message.thread_id for message in claimed_messages} == {
        first_thread,
        second_thread,
    }
    first_claim = next(
        message for message in claimed_messages if message.id == first_message
    )
    assert first_claim.claim_token is not None
    assert await mark_done(first_claim.id, first_claim.claim_token, "ok")

    next_message = await claim_next()

    assert next_message is not None
    assert next_message.thread_id == first_thread


async def test_stale_claim_token_cannot_complete_a_reclaimed_message(queue_user: UUID):
    thread_id = f"stale-token-{uuid4().hex}"
    message_id = await _enqueue_message(queue_user, thread_id, "mensagem")
    claimed = await claim_next()

    assert claimed is not None
    assert claimed.id == message_id
    assert claimed.claim_token is not None
    assert not await mark_done(message_id, uuid4(), "resposta antiga")
    assert await mark_done(message_id, claimed.claim_token, "resposta atual")


async def test_processing_lock_serializes_workers_for_the_same_thread():
    thread_id = f"lock-test-{uuid4().hex}"
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()

    async def first_worker() -> None:
        async with hold_thread_processing_lock(thread_id):
            first_started.set()
            await release_first.wait()

    async def second_worker() -> None:
        async with hold_thread_processing_lock(thread_id):
            second_started.set()

    first_task = asyncio.create_task(first_worker())
    await first_started.wait()
    second_task = asyncio.create_task(second_worker())
    await asyncio.sleep(0.05)
    assert not second_started.is_set()

    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert second_started.is_set()
