"""Testes do nó de catch-up no grafo, sem banco.

O que importa aqui não é o que o nó gera — isso é coberto pelos testes de
integração do repositório —, mas o que ele **não** faz: falhar em voz alta e
tocar na resposta entregue ao usuário.

Rodar só estes:
    uv run pytest tests/unit/test_catch_up_recurring_expenses_node.py
"""

from typing import cast
from uuid import uuid4

import pytest

from financial_agent.agent import build_graph_workflow
from financial_agent.agent.build_graph_workflow import catch_up_recurring_expenses
from financial_agent.agent.state_graph import GraphState
from shared.repositories.recurring_expenses import MaterializationResult

pytestmark = pytest.mark.asyncio


def _state() -> GraphState:
    return cast(
        GraphState,
        {
            "messages": [],
            "phone_number": "+5511999999999",
            "channel": "telegram",
            "user_id": str(uuid4()),
            "user_name": "Teste",
            "user_timezone": "America/Sao_Paulo",
        },
    )


async def test_a_database_failure_is_absorbed_and_the_flow_continues(  # TC-019
    monkeypatch,
):
    async def explode(**_kwargs):
        raise ConnectionError("Postgres indisponível")

    monkeypatch.setattr(
        build_graph_workflow, "materialize_due_recurring_expenses", explode
    )

    delta = await catch_up_recurring_expenses(_state())

    assert delta == {}


async def test_the_node_only_reports_diagnostics(monkeypatch):  # REQ-029, CON-006
    async def materialize(**_kwargs):
        return MaterializationResult(
            generated=[], rules_processed=3, truncated_rules=[]
        )

    monkeypatch.setattr(
        build_graph_workflow, "materialize_due_recurring_expenses", materialize
    )

    delta = await catch_up_recurring_expenses(_state())

    assert delta == {"materialized_recurring_expenses": 0}
    assert "response_text" not in delta
    assert "messages" not in delta


async def test_the_catch_up_runs_between_user_setup_and_pending_expiration():  # REQ-028
    graph = build_graph_workflow.build_workflow().compile()
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}

    assert ("ensure_user_node", "catch_up_recurring_expenses") in edges
    assert ("catch_up_recurring_expenses", "expire_pending_expenses") in edges
