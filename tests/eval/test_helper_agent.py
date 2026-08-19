"""Testes do adaptador de evals para o grafo do agente."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from eval.helper_agent import helper_agent_json


@pytest.mark.asyncio
async def test_helper_agent_awaits_graph_factory_and_serializes_result():
    compiled_graph = Mock()
    compiled_graph.ainvoke = AsyncMock(
        return_value={
            "extracted_expenses": [],
            "needs_clarification": False,
            "clarification_message": None,
        }
    )
    graph_factory = AsyncMock(return_value=compiled_graph)

    with patch("eval.helper_agent.Graph", graph_factory):
        result = await helper_agent_json("Gastei 35 reais no almoço")

    graph_factory.assert_awaited_once_with()
    compiled_graph.ainvoke.assert_awaited_once()
    assert result == (
        '{"expenses":[],"needs_clarification":false,"clarification_message":null}'
    )
