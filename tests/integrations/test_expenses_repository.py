"""Testes de integração do repositório de gastos.

Exigem um Postgres acessível em ``settings.database_url`` com as migrations de
``db/migrations`` aplicadas. Quando o banco não responde, o módulo inteiro é
pulado — assim ``make test`` continua verde em máquina sem infra.

Rodar só estes:
    uv run pytest -m db
"""

from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
import pytest_asyncio

from financial_agent.agent.state_graph import ExpenseDetails
from financial_agent.agent.tools.calendar import user_now
from shared.config import settings
from shared.db import close_pool, connection
from shared.repositories.categories import list_available_categories
from shared.repositories.expenses import get_last_expense, insert_expenses

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
async def two_users():
    """Cria dois usuários descartáveis e remove tudo o que eles geraram."""
    suffix = uuid4().hex[:10]
    created: list[UUID] = []

    async with connection() as conn:
        for index in (1, 2):
            cur = await conn.execute(
                """
                INSERT INTO "user" (channel, external_user_id, name, timezone)
                VALUES ('telegram', %s, %s, 'America/Sao_Paulo')
                RETURNING id
                """,
                (f"test-{suffix}-{index}", f"Teste {index}"),
            )
            row = await cur.fetchone()
            created.append(row["id"])

    yield created

    async with connection() as conn:
        await conn.execute(
            "DELETE FROM expense_audit_log WHERE user_id = ANY(%s)", (created,)
        )
        await conn.execute("DELETE FROM expense WHERE user_id = ANY(%s)", (created,))
        await conn.execute(
            "DELETE FROM message_queue WHERE user_id = ANY(%s)", (created,)
        )
        await conn.execute('DELETE FROM "user" WHERE id = ANY(%s)', (created,))


async def _enqueue_message(user_id: UUID) -> UUID:
    async with connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO message_queue
                (user_id, phone_number, agent_id, thread_id, incoming_message)
            VALUES (%s, 'test', 'add_new_expenses', %s, 'gastei 35 no almoço')
            RETURNING id
            """,
            (user_id, f"thread-{user_id}"),
        )
        row = await cur.fetchone()

    return row["id"]


async def _make_expense(user_id: UUID, amount: str = "35.00") -> ExpenseDetails:
    categories = await list_available_categories(user_id)
    assert categories, "Rode `make sync-categories` antes dos testes de integração"

    return ExpenseDetails(
        description="almoço",
        original_description="almoço",
        amount=Decimal(amount),
        occurred_at=user_now("America/Sao_Paulo"),
        category_id=categories[0].id,
        category_name=categories[0].name,
        payment_method="pix",
        confidence=0.95,
    )


async def test_insert_persists_the_expense(two_users):
    user_id = two_users[0]
    expense = await _make_expense(user_id)

    records = await insert_expenses(user_id, [expense])

    assert len(records) == 1
    assert records[0].amount == Decimal("35.00")
    assert isinstance(records[0].amount, Decimal)
    assert records[0].payment_method == "pix"


async def test_reprocessing_the_same_message_does_not_duplicate(two_users):
    """Retry do worker / reenvio do webhook não pode criar gasto duplicado."""
    user_id = two_users[0]
    message_id = await _enqueue_message(user_id)
    expense = await _make_expense(user_id)

    first = await insert_expenses(user_id, [expense], source_message_id=message_id)
    second = await insert_expenses(user_id, [expense], source_message_id=message_id)

    assert [r.id for r in first] == [r.id for r in second]

    async with connection() as conn:
        cur = await conn.execute(
            "SELECT count(*) AS total FROM expense WHERE source_message_id = %s",
            (message_id,),
        )
        assert (await cur.fetchone())["total"] == 1


async def test_multiple_expenses_from_one_message_are_all_saved(two_users):
    user_id = two_users[0]
    message_id = await _enqueue_message(user_id)
    expenses = [
        await _make_expense(user_id, "30.00"),
        await _make_expense(user_id, "50.00"),
    ]

    records = await insert_expenses(user_id, expenses, source_message_id=message_id)

    assert len(records) == 2
    assert sum(r.amount for r in records) == Decimal("80.00")


async def test_expenses_are_isolated_per_user(two_users):
    owner, other = two_users
    await insert_expenses(owner, [await _make_expense(owner)])

    assert await get_last_expense(owner) is not None
    assert await get_last_expense(other) is None


async def test_insert_writes_an_audit_row(two_users):
    user_id = two_users[0]
    records = await insert_expenses(user_id, [await _make_expense(user_id)])

    async with connection() as conn:
        cur = await conn.execute(
            """
            SELECT action, after_data
            FROM expense_audit_log
            WHERE expense_id = %s
            """,
            (records[0].id,),
        )
        row = await cur.fetchone()

    assert row["action"] == "created"
    assert row["after_data"]["amount"] == "35.00"


async def test_empty_list_is_a_noop(two_users):
    assert await insert_expenses(two_users[0], []) == []
