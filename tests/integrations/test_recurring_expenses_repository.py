"""Testes de integração do repositório de gastos fixos.

Exigem um Postgres acessível em ``settings.database_url`` com as migrations de
``db/migrations`` aplicadas. Quando o banco não responde, o módulo inteiro é
pulado — assim ``make test`` continua verde em máquina sem infra.

Rodar só estes:
    uv run pytest -m db tests/integrations/test_recurring_expenses_repository.py
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
import pytest_asyncio

from financial_agent.agent.state_graph import RecurringExpenseDetails
from shared.config import settings
from shared.db import close_pool, connection
from shared.repositories.categories import list_available_categories
from shared.repositories.recurring_expenses import (
    find_active_by_normalized_description,
    insert_recurring_expenses,
    list_active_recurring_expenses,
)

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
                (f"test-rec-{suffix}-{index}", f"Teste {index}"),
            )
            row = await cur.fetchone()
            created.append(row["id"])

    yield created

    async with connection() as conn:
        await conn.execute(
            "DELETE FROM recurring_expense WHERE user_id = ANY(%s)", (created,)
        )
        await conn.execute('DELETE FROM "user" WHERE id = ANY(%s)', (created,))


async def _make_rule(
    user_id: UUID,
    description: str = "Netflix",
    amount: str = "55.00",
    recurrence_day: int = 10,
    starts_at: date | None = None,
) -> RecurringExpenseDetails:
    categories = await list_available_categories(user_id)
    assert categories, "Rode `make sync-categories` antes dos testes de integração"

    return RecurringExpenseDetails(
        description=description,
        original_description=description,
        amount=Decimal(amount),
        category_id=categories[0].id,
        category_name=categories[0].name,
        payment_method="not_informed",
        recurrence_day=recurrence_day,
        starts_at=starts_at or date(2026, 8, 31),
        confidence=0.95,
    )


async def _deactivate(rule_id: UUID) -> None:
    async with connection() as conn:
        await conn.execute(
            "UPDATE recurring_expense SET is_active = FALSE WHERE id = %s", (rule_id,)
        )


async def test_insert_persists_the_rule_with_the_schema_defaults(two_users):
    user_id = two_users[0]

    result = await insert_recurring_expenses(user_id, [await _make_rule(user_id)])

    assert len(result.inserted) == 1
    record = result.inserted[0]
    assert record.amount == Decimal("55.00")
    assert isinstance(record.amount, Decimal)
    assert record.recurrence_day == 10
    assert record.ends_at is None  # CON-010
    assert result.duplicates == []

    active = await list_active_recurring_expenses(user_id)
    assert [rule.id for rule in active] == [record.id]  # CON-011


async def test_day_31_is_stored_without_clamp(two_users):  # TC-018
    user_id = two_users[0]

    result = await insert_recurring_expenses(
        user_id,
        [await _make_rule(user_id, description="aluguel", recurrence_day=31)],
    )

    assert result.inserted[0].recurrence_day == 31


async def test_future_start_date_is_stored_as_given(two_users):  # TC-015
    user_id = two_users[0]

    result = await insert_recurring_expenses(
        user_id, [await _make_rule(user_id, starts_at=date(2026, 10, 1))]
    )

    assert result.inserted[0].starts_at == date(2026, 10, 1)


async def test_a_duplicate_description_is_blocked(two_users):  # TC-011
    user_id = two_users[0]
    first = await insert_recurring_expenses(user_id, [await _make_rule(user_id)])

    second = await insert_recurring_expenses(
        user_id, [await _make_rule(user_id, description="netflix")]
    )

    assert second.inserted == []
    assert [rule.id for rule in second.duplicates] == [first.inserted[0].id]
    assert len(await list_active_recurring_expenses(user_id)) == 1


async def test_a_duplicate_with_a_different_amount_is_also_blocked(two_users):  # TC-012
    user_id = two_users[0]
    await insert_recurring_expenses(user_id, [await _make_rule(user_id)])

    second = await insert_recurring_expenses(
        user_id, [await _make_rule(user_id, amount="62.00", recurrence_day=20)]
    )

    assert second.inserted == []  # CON-016
    assert second.duplicates[0].amount == Decimal("55.00")


async def test_an_inactive_rule_does_not_block_a_new_one(two_users):  # TC-013
    user_id = two_users[0]
    first = await insert_recurring_expenses(user_id, [await _make_rule(user_id)])
    await _deactivate(first.inserted[0].id)

    second = await insert_recurring_expenses(user_id, [await _make_rule(user_id)])

    assert len(second.inserted) == 1
    assert second.duplicates == []


async def test_two_identical_rules_in_one_batch_insert_only_once(two_users):
    user_id = two_users[0]

    result = await insert_recurring_expenses(
        user_id,
        [await _make_rule(user_id), await _make_rule(user_id, description="NETFLIX")],
    )

    assert len(result.inserted) == 1
    assert len(result.duplicates) == 1


async def test_reprocessing_the_same_message_creates_no_new_row(two_users):  # TC-019
    user_id = two_users[0]
    message_id = uuid4()

    first = await insert_recurring_expenses(
        user_id, [await _make_rule(user_id)], source_message_id=message_id
    )
    second = await insert_recurring_expenses(
        user_id, [await _make_rule(user_id)], source_message_id=message_id
    )

    assert len(first.inserted) == 1
    assert second.inserted == []
    assert len(await list_active_recurring_expenses(user_id)) == 1


async def test_empty_input_touches_nothing(two_users):
    result = await insert_recurring_expenses(two_users[0], [])

    assert result.inserted == [] and result.duplicates == []


async def test_find_by_normalized_description_ignores_case_and_accents(two_users):
    user_id = two_users[0]
    await insert_recurring_expenses(
        user_id, [await _make_rule(user_id, description="Academia")]
    )

    found = await find_active_by_normalized_description(user_id, "  ACADEMIA ")

    assert found is not None and found.description == "Academia"
    assert await find_active_by_normalized_description(user_id, "Netflix") is None


async def test_users_never_see_each_others_rules(two_users):  # TC-021
    first_user, second_user = two_users
    await insert_recurring_expenses(first_user, [await _make_rule(first_user)])

    assert await list_active_recurring_expenses(second_user) == []
    assert await find_active_by_normalized_description(second_user, "Netflix") is None

    result = await insert_recurring_expenses(
        second_user, [await _make_rule(second_user)]
    )
    assert len(result.inserted) == 1
