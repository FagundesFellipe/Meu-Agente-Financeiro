"""Integração das agregações SQL do agente relator."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
import pytest
import pytest_asyncio

from financial_agent.agent.state_graph import ExpenseDetails
from financial_agent.agent.tools.period import ResolvedPeriod
from shared.config import settings
from shared.db import close_pool, connection
from shared.repositories.categories import list_available_categories
from shared.repositories.expense_reports import (
    largest_category_with_top_expense,
    largest_expense,
    list_expenses_page,
    list_expenses_page_for_periods,
    sum_by_category,
    sum_expenses,
    sum_expenses_for_periods,
)
from shared.repositories.expenses import insert_expenses

pytestmark = pytest.mark.db
ZONE = ZoneInfo("America/Sao_Paulo")


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
async def report_user():
    suffix = uuid4().hex[:10]
    async with connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO "user" (channel, external_user_id, name, timezone)
            VALUES ('telegram', %s, 'Relator', 'America/Sao_Paulo')
            RETURNING id
            """,
            (f"report-{suffix}",),
        )
        user_id = (await cur.fetchone())["id"]
    yield user_id
    async with connection() as conn:
        await conn.execute(
            "DELETE FROM expense_audit_log WHERE user_id = %s", (user_id,)
        )
        await conn.execute("DELETE FROM expense WHERE user_id = %s", (user_id,))
        await conn.execute('DELETE FROM "user" WHERE id = %s', (user_id,))


async def _seed(user_id: UUID) -> tuple[datetime, UUID]:
    categories = await list_available_categories(user_id)
    assert categories
    occurred_at = datetime(2026, 8, 5, 12, tzinfo=ZONE)
    await insert_expenses(
        user_id,
        [
            ExpenseDetails(
                description="almoço",
                original_description="almoço",
                amount=Decimal("35.00"),
                occurred_at=occurred_at,
                category_id=categories[0].id,
                category_name=categories[0].name,
                payment_method="pix",
            ),
            ExpenseDetails(
                description="jantar",
                original_description="jantar",
                amount=Decimal("55.00"),
                occurred_at=occurred_at + timedelta(hours=7),
                category_id=categories[0].id,
                category_name=categories[0].name,
                payment_method="credit_card",
            ),
        ],
    )
    return occurred_at, categories[0].id


async def test_report_queries_aggregate_filter_page_and_rank(report_user):
    occurred_at, category_id = await _seed(report_user)
    start = occurred_at.replace(hour=0)
    end = start + timedelta(days=1)

    assert await sum_expenses(report_user, start, end) == (Decimal("90.00"), 2)
    assert await sum_expenses(report_user, start, end, payment_method="pix") == (
        Decimal("35.00"),
        1,
    )
    rows, total_count = await list_expenses_page(
        report_user, start, end, category_id, None, 1, 0
    )
    assert total_count == 2 and rows[0].description == "jantar"
    totals = await sum_by_category(report_user, start, end)
    assert totals[0].total == Decimal("90.00")
    assert (await largest_expense(report_user, start, end)).amount == Decimal("55.00")
    top_category, top_expense = await largest_category_with_top_expense(
        report_user, start, end
    )
    assert top_category is not None and top_category.total == Decimal("90.00")
    assert top_expense is not None and top_expense.amount == Decimal("55.00")

    periods = [
        ResolvedPeriod("almoço", "day", start.replace(hour=11), start.replace(hour=13)),
        ResolvedPeriod("jantar", "day", start.replace(hour=18), start.replace(hour=20)),
    ]
    assert await sum_expenses_for_periods(report_user, periods) == (
        Decimal("90.00"),
        2,
    )
    merged_rows, merged_count = await list_expenses_page_for_periods(
        report_user, periods, None, None, 10, 0
    )
    assert merged_count == 2 and len(merged_rows) == 2
