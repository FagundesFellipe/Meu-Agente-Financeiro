"""Testes de integração do repositório de usuários.

Exigem um Postgres acessível em ``settings.database_url`` com as migrations de
``db/migrations`` aplicadas (identidade por ``(channel, external_user_id)``).
Quando o banco não responde, o módulo inteiro é pulado — assim ``make test``
continua verde em máquina sem infra.

Rodar só estes:
    uv run pytest -m db tests/integrations/test_users_repository.py
"""

import asyncio
from uuid import UUID, uuid4

import psycopg
import pytest
import pytest_asyncio

from shared.config import settings
from shared.db import close_pool, connection
from shared.repositories.users import ensure_user

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


@pytest_asyncio.fixture
async def suffix():
    """Sufixo único por teste, para não colidir com outros testes/execuções."""
    return uuid4().hex[:10]


@pytest_asyncio.fixture
async def created_users():
    """Coleciona ids criados durante o teste e apaga tudo ao final."""
    created: list[UUID] = []

    yield created

    if not created:
        return

    async with connection() as conn:
        await conn.execute('DELETE FROM "user" WHERE id = ANY(%s)', (created,))


async def test_first_call_creates_user_second_call_reuses_it(suffix, created_users):
    external_user_id = f"test-{suffix}"

    first_user, first_created = await ensure_user("whatsapp", external_user_id)
    created_users.append(first_user.id)

    second_user, second_created = await ensure_user("whatsapp", external_user_id)

    assert first_created is True
    assert second_created is False
    assert second_user.id == first_user.id


async def test_different_external_ids_on_same_channel_are_distinct_users(
    suffix, created_users
):
    user_a, _ = await ensure_user("whatsapp", f"test-{suffix}-a")
    created_users.append(user_a.id)
    user_b, _ = await ensure_user("whatsapp", f"test-{suffix}-b")
    created_users.append(user_b.id)

    assert user_a.id != user_b.id


async def test_same_external_id_on_different_channels_are_distinct_users(
    suffix, created_users
):
    """Não existe fusão de identidade entre canais — decisão de produto explícita."""
    external_user_id = f"test-{suffix}"

    whatsapp_user, _ = await ensure_user("whatsapp", external_user_id)
    created_users.append(whatsapp_user.id)
    telegram_user, _ = await ensure_user("telegram", external_user_id)
    created_users.append(telegram_user.id)

    assert whatsapp_user.id != telegram_user.id
    assert whatsapp_user.channel == "whatsapp"
    assert telegram_user.channel == "telegram"


async def test_concurrent_ensure_user_does_not_create_duplicate_rows(
    suffix, created_users
):
    """O lock consultivo evita corrida entre requisições concorrentes."""
    channel = "whatsapp"
    external_user_id = f"test-{suffix}"

    results = await asyncio.gather(
        ensure_user(channel, external_user_id),
        ensure_user(channel, external_user_id),
    )

    (user_a, created_a), (user_b, created_b) = results
    created_users.append(user_a.id)
    if user_b.id != user_a.id:
        created_users.append(user_b.id)

    assert user_a.id == user_b.id
    assert {created_a, created_b} == {True, False}

    async with connection() as conn:
        cur = await conn.execute(
            """
            SELECT count(*) AS total
            FROM "user"
            WHERE channel = %s AND external_user_id = %s
            """,
            (channel, external_user_id),
        )
        row = await cur.fetchone()
        assert row is not None
        assert row["total"] == 1
