"""Testes do adaptador de avaliação da extração pura de despesas."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from eval.evaluate_expense_adaptor import (
    evaluate_expense_exctraction,
)
from financial_agent.agent.state_graph import AddExpensesResult, PendingExpense
from shared.categories import GLOBAL_CATEGORIES


@pytest.mark.asyncio
async def test_adapter_calls_only_expense_extraction_agent_and_serializes_response():
    structured_response = AddExpensesResult(
        expenses=[],
        pending_expenses=[
            PendingExpense(
                description="almoço",
                amount_raw=None,
                missing_fields=["amount"],
                clarification_message="Qual foi o valor do almoço?",
            )
        ],
    )
    agent = Mock()
    agent.ainvoke = AsyncMock(return_value={"structured_response": structured_response})

    with patch(
        "eval.evaluate_expense_adaptor.build_add_expenses_agent", return_value=agent
    ):
        result = await evaluate_expense_exctraction("Gastei 35 reais no almoço")

    agent.ainvoke.assert_awaited_once()
    messages = agent.ainvoke.await_args.args[0]["messages"]

    assert isinstance(messages[0], SystemMessage)
    assert "DATA_HORA_ATUAL: 2026-08-26T12:00:00-03:00" in messages[0].content
    assert all(category.name in messages[0].content for category in GLOBAL_CATEGORIES)
    assert messages[1] == HumanMessage(content="Gastei 35 reais no almoço")
    assert result == structured_response.model_dump_json()
