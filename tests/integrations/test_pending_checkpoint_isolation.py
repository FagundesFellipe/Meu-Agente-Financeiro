"""Persistência de pendências no checkpointer PostgreSQL por ``thread_id``."""

from uuid import uuid4

import psycopg
import pytest
import pytest_asyncio
from langchain_core.messages import HumanMessage

from financial_agent.agent import build_graph_workflow as workflow_module
from financial_agent.agent.state_graph import PendingExpense
from shared.config import settings
from shared.db import (
    bootstrap_langgraph_schema,
    close_checkpointer,
    close_pool,
    connection,
    get_checkpointer,
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
    await close_checkpointer()
    await close_pool()


async def _delete_checkpoints(thread_ids: list[str]) -> None:
    async with connection() as conn:
        await conn.execute(
            "DELETE FROM checkpoint_writes WHERE thread_id = ANY(%s)", (thread_ids,)
        )
        await conn.execute(
            "DELETE FROM checkpoints WHERE thread_id = ANY(%s)", (thread_ids,)
        )


async def test_pending_expenses_are_isolated_by_checkpoint_thread_id(monkeypatch):
    pending = PendingExpense(
        id="pending-geladeira",
        description="geladeira",
        amount_raw="5000",
        amount_is_total=True,
        missing_fields=["installments"],
        clarification_message="Em quantas vezes foi a geladeira?",
    )
    resolved_pending_ids: list[str | None] = []

    async def ensure_user(_: dict) -> dict:
        return {
            "user_id": str(uuid4()),
            "user_name": None,
            "user_timezone": "America/Sao_Paulo",
            "is_new_user": False,
        }

    async def route(state: dict) -> dict:
        message = state["messages"][-1]
        content = str(getattr(message, "content", ""))
        intention = (
            "continue_pending_expense"
            if content == "em 3 vezes"
            else "add_new_expenses"
        )
        return {"intention": intention}

    async def add_expense(_: dict) -> dict:
        return {
            "pending_expenses": [pending],
            "needs_clarification": True,
            "response_text": pending.clarification_message,
        }

    async def resolve_pending(state: dict) -> dict:
        pending_expenses = state.get("pending_expenses", [])
        resolved_pending_ids.append(
            pending_expenses[0].id if pending_expenses else None
        )
        return {
            "pending_expenses": [],
            "needs_clarification": False,
            "response_text": "Pendência resolvida.",
        }

    monkeypatch.setattr(workflow_module, "ensure_user_node", ensure_user)
    monkeypatch.setattr(workflow_module, "llm_call_router", route)
    monkeypatch.setattr(workflow_module, "add_new_expenses", add_expense)
    monkeypatch.setattr(workflow_module, "resolve_pending_expenses", resolve_pending)

    first_thread = f"pending-checkpoint-{uuid4().hex}"
    second_thread = f"pending-checkpoint-{uuid4().hex}"
    await bootstrap_langgraph_schema()
    graph = workflow_module.build_workflow().compile(
        checkpointer=await get_checkpointer()
    )
    try:
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="comprei uma geladeira")],
                "phone_number": "111",
                "channel": "telegram",
            },
            config={"configurable": {"thread_id": first_thread}},
        )
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="em 3 vezes")],
                "phone_number": "222",
                "channel": "telegram",
            },
            config={"configurable": {"thread_id": second_thread}},
        )
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="em 3 vezes")],
                "phone_number": "111",
                "channel": "telegram",
            },
            config={"configurable": {"thread_id": first_thread}},
        )
    finally:
        await _delete_checkpoints([first_thread, second_thread])

    assert resolved_pending_ids == [None, "pending-geladeira"]
