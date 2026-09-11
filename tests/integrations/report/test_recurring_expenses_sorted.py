"""Ordenação determinística da listagem de gastos fixos."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from shared.repositories import recurring_expenses
from shared.repositories.recurring_expenses import RecurringExpenseRecord


def rule(description: str) -> RecurringExpenseRecord:
    return RecurringExpenseRecord(
        id=uuid4(),
        description=description,
        amount=Decimal("10.00"),
        payment_method="not_informed",
        recurrence_day=10,
        starts_at=date(2026, 1, 1),
        ends_at=None,
        category_id=uuid4(),
        category_name="Outros gastos",
    )


@pytest.mark.asyncio
async def test_sorts_active_rules_ignoring_accents_and_case(monkeypatch):
    async def fake_list(_user_id):
        return [rule("Zoológico"), rule("academia"), rule("Água")]

    monkeypatch.setattr(recurring_expenses, "list_active_recurring_expenses", fake_list)

    result = await recurring_expenses.list_active_recurring_expenses_sorted(uuid4())

    assert [item.description for item in result] == ["academia", "Água", "Zoológico"]
