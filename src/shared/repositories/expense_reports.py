"""Consultas determinísticas e somente leitura para relatórios de gastos."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from financial_agent.agent.state_graph import PaymentMethod
from financial_agent.agent.tools.period import ResolvedPeriod
from shared.db import DictConnection, user_connection
from shared.repositories.expenses import ExpenseRecord, to_expense_record

_BASE_FILTER = """
    e.user_id = %(user_id)s
    AND e.occurred_at >= %(start)s
    AND e.occurred_at < %(end)s
    AND (%(category_id)s::uuid IS NULL OR e.category_id = %(category_id)s::uuid)
    AND (%(payment_method)s::text IS NULL OR e.payment_method = %(payment_method)s)
"""

_SUM_EXPENSES = f"""
    SELECT COALESCE(SUM(e.amount), 0) AS total, COUNT(*) AS count
    FROM expense e
    WHERE {_BASE_FILTER}
"""

_LIST_EXPENSES_PAGE = f"""
    SELECT e.id, e.amount, e.description, e.original_description,
           e.payment_method, e.occurred_at, e.category_id,
           e.installment_number, e.total_installments, e.recurrence_period,
           c.name AS category_name, COUNT(*) OVER() AS total_count
    FROM expense e
    JOIN category c ON c.id = e.category_id
    WHERE {_BASE_FILTER}
    ORDER BY e.occurred_at DESC, e.id DESC
    LIMIT %(limit)s OFFSET %(offset)s
"""

_SUM_BY_CATEGORY = """
    SELECT c.id AS category_id, c.name AS category_name,
           COALESCE(SUM(e.amount), 0) AS total, COUNT(*) AS count
    FROM expense e
    JOIN category c ON c.id = e.category_id
    WHERE e.user_id = %(user_id)s
      AND e.occurred_at >= %(start)s
      AND e.occurred_at < %(end)s
      AND (%(category_id)s::uuid IS NULL OR e.category_id = %(category_id)s::uuid)
      AND (%(payment_method)s::text IS NULL OR e.payment_method = %(payment_method)s)
    GROUP BY c.id, c.name
    ORDER BY total DESC, c.name
"""

_LARGEST_EXPENSE = f"""
    SELECT e.id, e.amount, e.description, e.original_description,
           e.payment_method, e.occurred_at, e.category_id,
           e.installment_number, e.total_installments, e.recurrence_period,
           c.name AS category_name
    FROM expense e
    JOIN category c ON c.id = e.category_id
    WHERE {_BASE_FILTER}
    ORDER BY e.amount DESC, e.occurred_at DESC, e.id DESC
    LIMIT 1
"""

_RANGES_FILTER = """
    e.user_id = %(user_id)s
    AND EXISTS (
        SELECT 1
        FROM unnest(
            %(starts)s::timestamptz[],
            %(ends)s::timestamptz[]
        ) AS report_range(start_at, end_at)
        WHERE e.occurred_at >= report_range.start_at
          AND e.occurred_at < report_range.end_at
    )
    AND (%(category_id)s::uuid IS NULL OR e.category_id = %(category_id)s::uuid)
    AND (%(payment_method)s::text IS NULL OR e.payment_method = %(payment_method)s)
"""

_SUM_EXPENSES_FOR_PERIODS = f"""
    SELECT COALESCE(SUM(e.amount), 0) AS total, COUNT(*) AS count
    FROM expense e
    WHERE {_RANGES_FILTER}
"""

_LIST_EXPENSES_FOR_PERIODS = f"""
    SELECT e.id, e.amount, e.description, e.original_description,
           e.payment_method, e.occurred_at, e.category_id,
           e.installment_number, e.total_installments, e.recurrence_period,
           c.name AS category_name, COUNT(*) OVER() AS total_count
    FROM expense e
    JOIN category c ON c.id = e.category_id
    WHERE {_RANGES_FILTER}
    ORDER BY e.occurred_at DESC, e.id DESC
    LIMIT %(limit)s OFFSET %(offset)s
"""

_SUM_BY_CATEGORY_FOR_PERIODS = f"""
    SELECT c.id AS category_id, c.name AS category_name,
           COALESCE(SUM(e.amount), 0) AS total, COUNT(*) AS count
    FROM expense e
    JOIN category c ON c.id = e.category_id
    WHERE {_RANGES_FILTER}
    GROUP BY c.id, c.name
    ORDER BY total DESC, c.name
"""


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    category_id: UUID
    category_name: str
    total: Decimal
    count: int


def _params(
    user_id: str | UUID,
    start: datetime,
    end: datetime,
    category_id: UUID | None = None,
    payment_method: PaymentMethod | None = None,
) -> dict:
    return {
        "user_id": str(user_id),
        "start": start,
        "end": end,
        "category_id": str(category_id) if category_id else None,
        "payment_method": payment_method,
    }


def _period_params(
    user_id: str | UUID,
    periods: list[ResolvedPeriod],
    category_id: UUID | None = None,
    payment_method: PaymentMethod | None = None,
) -> dict:
    return {
        "user_id": str(user_id),
        "starts": [period.start for period in periods],
        "ends": [period.end for period in periods],
        "category_id": str(category_id) if category_id else None,
        "payment_method": payment_method,
    }


async def sum_expenses(
    user_id: str | UUID,
    start: datetime,
    end: datetime,
    category_id: UUID | None = None,
    payment_method: PaymentMethod | None = None,
) -> tuple[Decimal, int]:
    async with user_connection(str(user_id)) as conn:
        cur = await conn.execute(
            _SUM_EXPENSES,
            _params(user_id, start, end, category_id, payment_method),
        )
        row = await cur.fetchone()
    if row is None:  # pragma: no cover - agregado sempre retorna uma linha
        return Decimal("0"), 0
    return row["total"], row["count"]


async def sum_expenses_for_periods(
    user_id: str | UUID,
    periods: list[ResolvedPeriod],
    category_id: UUID | None = None,
    payment_method: PaymentMethod | None = None,
) -> tuple[Decimal, int]:
    """Agrega a união de períodos numa única consulta, sem somar em Python."""
    async with user_connection(str(user_id)) as conn:
        cur = await conn.execute(
            _SUM_EXPENSES_FOR_PERIODS,
            _period_params(user_id, periods, category_id, payment_method),
        )
        row = await cur.fetchone()
    if row is None:  # pragma: no cover
        return Decimal("0"), 0
    return row["total"], row["count"]


async def list_expenses_page(
    user_id: str | UUID,
    start: datetime,
    end: datetime,
    category_id: UUID | None,
    payment_method: PaymentMethod | None,
    limit: int,
    offset: int,
) -> tuple[list[ExpenseRecord], int]:
    params = _params(user_id, start, end, category_id, payment_method)
    params.update({"limit": limit, "offset": offset})
    async with user_connection(str(user_id)) as conn:
        cur = await conn.execute(_LIST_EXPENSES_PAGE, params)
        rows = await cur.fetchall()
    records = [to_expense_record(row, row["category_name"]) for row in rows]
    return records, rows[0]["total_count"] if rows else 0


async def list_expenses_page_for_periods(
    user_id: str | UUID,
    periods: list[ResolvedPeriod],
    category_id: UUID | None,
    payment_method: PaymentMethod | None,
    limit: int,
    offset: int,
) -> tuple[list[ExpenseRecord], int]:
    params = _period_params(user_id, periods, category_id, payment_method)
    params.update({"limit": limit, "offset": offset})
    async with user_connection(str(user_id)) as conn:
        cur = await conn.execute(_LIST_EXPENSES_FOR_PERIODS, params)
        rows = await cur.fetchall()
    records = [to_expense_record(row, row["category_name"]) for row in rows]
    return records, rows[0]["total_count"] if rows else 0


async def _sum_by_category(
    conn: DictConnection,
    user_id: str | UUID,
    start: datetime,
    end: datetime,
    category_id: UUID | None,
    payment_method: PaymentMethod | None,
) -> list[CategoryTotal]:
    cur = await conn.execute(
        _SUM_BY_CATEGORY,
        _params(user_id, start, end, category_id, payment_method),
    )
    rows = await cur.fetchall()
    return [
        CategoryTotal(
            category_id=row["category_id"],
            category_name=row["category_name"],
            total=row["total"],
            count=row["count"],
        )
        for row in rows
    ]


async def sum_by_category(
    user_id: str | UUID,
    start: datetime,
    end: datetime,
    payment_method: PaymentMethod | None = None,
) -> list[CategoryTotal]:
    async with user_connection(str(user_id)) as conn:
        return await _sum_by_category(conn, user_id, start, end, None, payment_method)


async def sum_by_category_for_periods(
    user_id: str | UUID,
    periods: list[ResolvedPeriod],
    payment_method: PaymentMethod | None = None,
) -> list[CategoryTotal]:
    async with user_connection(str(user_id)) as conn:
        cur = await conn.execute(
            _SUM_BY_CATEGORY_FOR_PERIODS,
            _period_params(user_id, periods, payment_method=payment_method),
        )
        rows = await cur.fetchall()
    return [
        CategoryTotal(
            category_id=row["category_id"],
            category_name=row["category_name"],
            total=row["total"],
            count=row["count"],
        )
        for row in rows
    ]


async def _largest_expense(
    conn: DictConnection,
    user_id: str | UUID,
    start: datetime,
    end: datetime,
    category_id: UUID | None,
    payment_method: PaymentMethod | None,
) -> ExpenseRecord | None:
    cur = await conn.execute(
        _LARGEST_EXPENSE,
        _params(user_id, start, end, category_id, payment_method),
    )
    row = await cur.fetchone()
    return to_expense_record(row, row["category_name"]) if row else None


async def largest_expense(
    user_id: str | UUID,
    start: datetime,
    end: datetime,
    category_id: UUID | None = None,
    payment_method: PaymentMethod | None = None,
) -> ExpenseRecord | None:
    async with user_connection(str(user_id)) as conn:
        return await _largest_expense(
            conn, user_id, start, end, category_id, payment_method
        )


async def largest_category_with_top_expense(
    user_id: str | UUID,
    start: datetime,
    end: datetime,
    category_id: UUID | None = None,
    payment_method: PaymentMethod | None = None,
) -> tuple[CategoryTotal | None, ExpenseRecord | None]:
    async with user_connection(str(user_id)) as conn:
        categories = await _sum_by_category(
            conn, user_id, start, end, category_id, payment_method
        )
        if not categories:
            return None, None
        top_category = categories[0]
        top_expense = await _largest_expense(
            conn,
            user_id,
            start,
            end,
            top_category.category_id,
            payment_method,
        )
    return top_category, top_expense
