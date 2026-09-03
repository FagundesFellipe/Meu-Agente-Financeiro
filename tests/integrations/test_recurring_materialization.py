"""Testes de integração da materialização de gastos fixos em lançamentos.

Exigem um Postgres acessível em ``settings.database_url`` com as migrations de
``db/migrations`` aplicadas, incluindo a 006. Quando o banco não responde, o
módulo inteiro é pulado — assim ``make test`` continua verde em máquina sem
infra.

Rodar só estes:
    uv run pytest -m db tests/integrations/test_recurring_materialization.py
"""

import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
import pytest
import pytest_asyncio

from financial_agent.agent.state_graph import RecurringExpenseDetails
from financial_agent.agent.tools.recurrence import (
    MAX_RETROACTIVE_PERIODS,
    effective_date,
)
from shared.config import settings
from shared.db import close_pool, connection
from shared.repositories.categories import list_available_categories
from shared.repositories.recurring_expenses import (
    insert_recurring_expenses,
    materialize_due_recurring_expenses,
)

pytestmark = pytest.mark.db

TIMEZONE = "America/Sao_Paulo"
ZONE = ZoneInfo(TIMEZONE)


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
                VALUES ('telegram', %s, %s, %s)
                RETURNING id
                """,
                (f"test-mat-{suffix}-{index}", f"Teste {index}", TIMEZONE),
            )
            row = await cur.fetchone()
            created.append(row["id"])

    yield created

    async with connection() as conn:
        await conn.execute(
            """
            DELETE FROM expense_audit_log WHERE user_id = ANY(%s)
            """,
            (created,),
        )
        await conn.execute("DELETE FROM expense WHERE user_id = ANY(%s)", (created,))
        await conn.execute(
            "DELETE FROM recurring_expense WHERE user_id = ANY(%s)", (created,)
        )
        await conn.execute('DELETE FROM "user" WHERE id = ANY(%s)', (created,))


async def _create_rule(
    user_id: UUID,
    description: str = "Netflix",
    amount: str = "55.00",
    recurrence_day: int = 10,
    starts_at: date = date(2026, 9, 1),
) -> UUID:
    """Grava uma regra ativa e devolve seu id."""
    categories = await list_available_categories(user_id)
    assert categories, "Rode `make sync-categories` antes dos testes de integração"

    result = await insert_recurring_expenses(
        user_id,
        [
            RecurringExpenseDetails(
                description=description,
                original_description=description,
                amount=Decimal(amount),
                category_id=categories[0].id,
                category_name=categories[0].name,
                payment_method="not_informed",
                recurrence_day=recurrence_day,
                starts_at=starts_at,
                confidence=0.95,
            )
        ],
    )
    return result.inserted[0].id


async def _update_rule(rule_id: UUID, **columns) -> None:
    assignments = ", ".join(f"{name} = %({name})s" for name in columns)
    async with connection() as conn:
        await conn.execute(
            f"UPDATE recurring_expense SET {assignments} WHERE id = %(id)s",
            {**columns, "id": rule_id},
        )


async def _count_expenses(rule_id: UUID) -> int:
    async with connection() as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) AS total FROM expense WHERE recurring_expense_id = %s",
            (rule_id,),
        )
        row = await cur.fetchone()
    return row["total"]


async def test_the_current_period_is_materialized_once(two_users):  # TC-001, AC-001
    user_id = two_users[0]
    rule_id = await _create_rule(user_id)

    result = await materialize_due_recurring_expenses(
        user_id, date(2026, 9, 15), TIMEZONE
    )

    assert len(result.generated) == 1
    assert result.rules_processed == 1
    assert result.truncated_rules == []

    expense = result.generated[0]
    assert expense.recurrence_period == date(2026, 9, 1)
    assert expense.amount == Decimal("55.00")
    assert isinstance(expense.amount, Decimal)
    assert expense.description == "Netflix"
    assert expense.original_description == "Netflix"
    assert await _count_expenses(rule_id) == 1


async def test_repeated_runs_do_not_duplicate(two_users):  # TC-002, AC-002
    user_id = two_users[0]
    rule_id = await _create_rule(user_id)
    today = date(2026, 9, 15)

    for _ in range(5):
        await materialize_due_recurring_expenses(user_id, today, TIMEZONE)

    assert await _count_expenses(rule_id) == 1


async def test_concurrent_runs_generate_exactly_one(two_users):  # TC-015, AC-011
    user_id = two_users[0]
    rule_id = await _create_rule(user_id)
    today = date(2026, 9, 15)

    results = await asyncio.gather(
        materialize_due_recurring_expenses(user_id, today, TIMEZONE),
        materialize_due_recurring_expenses(user_id, today, TIMEZONE),
    )

    assert sum(len(result.generated) for result in results) == 1
    assert await _count_expenses(rule_id) == 1


async def test_a_backlog_is_truncated_and_resumed(two_users):  # TC-008, TC-009
    user_id = two_users[0]
    rule_id = await _create_rule(user_id, starts_at=date(2024, 9, 1))
    today = date(2026, 9, 15)

    first = await materialize_due_recurring_expenses(user_id, today, TIMEZONE)

    assert len(first.generated) == MAX_RETROACTIVE_PERIODS
    assert first.truncated_rules == [rule_id]
    assert [expense.recurrence_period for expense in first.generated] == sorted(
        expense.recurrence_period for expense in first.generated
    )

    await materialize_due_recurring_expenses(user_id, today, TIMEZONE)
    third = await materialize_due_recurring_expenses(user_id, today, TIMEZONE)

    assert third.truncated_rules == []
    assert await _count_expenses(rule_id) == 25


async def test_an_inactive_rule_is_ignored(two_users):  # TC-010, AC-008
    user_id = two_users[0]
    rule_id = await _create_rule(user_id)
    await _update_rule(rule_id, is_active=False)

    result = await materialize_due_recurring_expenses(
        user_id, date(2026, 9, 15), TIMEZONE
    )

    assert result.generated == []
    assert result.rules_processed == 0


async def test_a_rule_that_already_ended_generates_nothing(two_users):  # TC-011
    user_id = two_users[0]
    rule_id = await _create_rule(user_id, starts_at=date(2026, 8, 1))
    await _update_rule(rule_id, ends_at=date(2026, 8, 31))

    result = await materialize_due_recurring_expenses(
        user_id, date(2026, 9, 15), TIMEZONE
    )

    assert [expense.recurrence_period for expense in result.generated] == [
        date(2026, 8, 1)
    ]


async def test_the_charge_day_survives_the_timezone_round_trip(two_users):  # TC-022
    user_id = two_users[0]
    await _create_rule(user_id, recurrence_day=10)

    result = await materialize_due_recurring_expenses(
        user_id, date(2026, 9, 15), TIMEZONE
    )

    async with connection() as conn:
        cur = await conn.execute(
            """
            SELECT (occurred_at AT TIME ZONE %s)::DATE AS charge_date
            FROM expense WHERE id = %s
            """,
            (TIMEZONE, result.generated[0].id),
        )
        row = await cur.fetchone()

    assert row["charge_date"] == date(2026, 9, 10)


async def test_february_clamps_the_charge_day(two_users):  # TC-004, AC-004
    user_id = two_users[0]
    await _create_rule(user_id, recurrence_day=31, starts_at=date(2026, 2, 1))

    result = await materialize_due_recurring_expenses(
        user_id, date(2026, 2, 28), TIMEZONE
    )

    charge = result.generated[0].occurred_at.astimezone(ZONE)
    assert charge.date() == date(2026, 2, 28)
    assert charge.hour == 12  # RAT-004


async def test_every_generated_expense_is_audited(two_users):  # TC-020, AC-015
    user_id = two_users[0]
    await _create_rule(user_id)
    result = await materialize_due_recurring_expenses(
        user_id, date(2026, 9, 15), TIMEZONE
    )

    async with connection() as conn:
        cur = await conn.execute(
            """
            SELECT action, source_message_id
            FROM expense_audit_log WHERE expense_id = %s
            """,
            (result.generated[0].id,),
        )
        rows = await cur.fetchall()

    assert len(rows) == 1
    assert rows[0]["action"] == "created"
    assert rows[0]["source_message_id"] is None


async def test_one_user_never_materializes_for_another(two_users):  # TC-021, AC-018
    owner, other = two_users
    rule_id = await _create_rule(owner)

    await materialize_due_recurring_expenses(other, date(2026, 9, 15), TIMEZONE)

    assert await _count_expenses(rule_id) == 0


async def test_a_duplicate_pair_is_rejected_by_the_database(two_users):  # TC-016
    user_id = two_users[0]
    await _create_rule(user_id)
    result = await materialize_due_recurring_expenses(
        user_id, date(2026, 9, 15), TIMEZONE
    )
    expense = result.generated[0]

    async with connection() as conn:
        with pytest.raises(psycopg.errors.UniqueViolation):
            await conn.execute(
                """
                INSERT INTO expense (
                    user_id, category_id, recurring_expense_id, recurrence_period,
                    amount, description, occurred_at
                )
                SELECT user_id, category_id, recurring_expense_id, recurrence_period,
                       amount, description, occurred_at
                FROM expense WHERE id = %s
                """,
                (expense.id,),
            )


async def test_an_inconsistent_pairing_is_rejected(two_users):  # TC-018
    user_id = two_users[0]
    categories = await list_available_categories(user_id)

    async with connection() as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            await conn.execute(
                """
                INSERT INTO expense (
                    user_id, category_id, recurrence_period,
                    amount, description, occurred_at
                )
                VALUES (%s, %s, %s, 10.00, 'inconsistente', NOW())
                """,
                (user_id, categories[0].id, date(2026, 9, 1)),
            )


async def test_a_one_off_expense_keeps_both_recurrence_columns_null(  # TC-017
    two_users,
):
    user_id = two_users[0]
    categories = await list_available_categories(user_id)

    async with connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO expense (user_id, category_id, amount, description, occurred_at)
            VALUES (%s, %s, 35.00, 'almoço', NOW())
            RETURNING recurring_expense_id, recurrence_period
            """,
            (user_id, categories[0].id),
        )
        row = await cur.fetchone()

    assert row["recurring_expense_id"] is None
    assert row["recurrence_period"] is None


async def test_the_python_clamp_matches_the_database_function():  # TC-014
    periods = [
        date(2026, month, 1) if month <= 12 else date(2027, month - 12, 1)
        for month in range(1, 25)
    ]

    async with connection() as conn:
        for period in periods:
            for day in range(28, 32):
                cur = await conn.execute(
                    "SELECT clamp_recurrence_day(%s, %s) AS day",
                    (day, period),
                )
                row = await cur.fetchone()
                assert row["day"] == effective_date(day, period).day, (
                    f"divergência em {period} dia {day}"
                )
