"""Constrói o workflow LangGraph — nós, arestas e roteamento por intenção.

Este módulo só monta o grafo; nenhuma execução acontece na importação.
Para inspecionar o desenho ou fazer um teste manual, use ``make graph`` ou
``python -m financial_agent.agent.build_graph_workflow``.
"""

from typing import Literal, cast

import structlog
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from financial_agent.agent.middleware.content_filter_before_agent import (
    ensure_input_content_safe,
)
from financial_agent.agent.middleware.trim import (
    create_trim_node,
    trim_messages_by_turns,
)
from financial_agent.agent.ReAct.add_new_expenses_agent import add_new_expenses
from financial_agent.agent.ReAct.add_recurring_expenses_agent import (
    add_recurring_expenses,
)
from financial_agent.agent.ReAct.resolve_pending_expenses_agent import (
    resolve_pending_expenses,
)
from financial_agent.agent.ReAct.resolve_pending_recurring_expenses_agent import (
    resolve_pending_recurring_expenses,
)
from financial_agent.agent.state_graph import GraphState, InputState, Intentions
from financial_agent.agent.tools import calendar as tools_calendar
from financial_agent.agent.tools.pending_expenses import split_expired_pending_expenses
from shared.agent_builder import build_agent_for_version
from shared.config import settings
from shared.db import open_checkpointer
from shared.prompt_loader import get_active_version, load_prompt_config
from shared.repositories.users import ensure_user

logger = structlog.get_logger()

_NOT_IMPLEMENTED_YET = (
    "Essa funcionalidade ainda está em construção. Por enquanto eu consigo "
    "registrar seus gastos — é só me dizer o que você gastou e quanto."
)
_GREETING = (
    "Oi! Sou seu assistente financeiro. Me conte um gasto que eu registro "
    "para você, por exemplo: “gastei 35 no almoço”."
)
_WELCOME_PREFIX = (
    "Seja bem-vindo(a) ao seu assistente financeiro! Você pode me contar "
    "seus gastos a qualquer momento, por exemplo: “gastei 35 no almoço”.\n\n"
    "Sobre o que você me chamou:"
)
_UNSAFE_INPUT_MESSAGE = (
    "Não posso ajudar com pedidos para ignorar instruções ou revelar "
    "configurações internas. Posso ajudar a registrar um gasto."
)


class RouteIntention(BaseModel):
    """Saída estruturada do roteador."""

    intentions_decision: Intentions


async def ensure_user_node(state: GraphState) -> dict:
    """Garante que o usuário existe, criando-o na primeira mensagem."""
    user, created = await ensure_user(state["channel"], state["phone_number"])
    return {
        "user_id": str(user.id),
        "user_name": user.name,
        "user_timezone": user.timezone,
        "is_new_user": created,
    }


async def finalize_response(state: GraphState) -> dict:
    """Prefixa a boas-vindas na primeira resposta e a adiciona como AIMessage."""
    response_text = state.get("response_text")
    if response_text and state.get("is_new_user"):
        response_text = f"{_WELCOME_PREFIX}\n\n{response_text}"

    if response_text is None:
        response_text = _NOT_IMPLEMENTED_YET

    return {
        "response_text": response_text,
        "messages": [AIMessage(content=response_text)],
    }


async def llm_call_router(state: GraphState) -> dict:
    ROUTER_PROMPT_NAME = "ROUTER_SYSTEM_PROMPT"

    """Classifica a intenção da mensagem do usuário."""

    version = get_active_version(ROUTER_PROMPT_NAME)
    agent = build_agent_for_version(
        prompt_name=ROUTER_PROMPT_NAME,
        version=version,
        response_format=ToolStrategy(RouteIntention),
        agent_name="llm_router",
    )

    load_prompt_config(ROUTER_PROMPT_NAME)

    trimmed_messages = trim_messages_by_turns(
        state["messages"], keep_turns=settings.trim_keep_tuns
    )

    result = await agent.ainvoke({"messages": trimmed_messages})
    route = cast(RouteIntention, result["structured_response"])

    return {"intention": route.intentions_decision}


def route_decision_intentions(state: GraphState) -> str:
    """Escolhe o nó de destino a partir da intenção classificada."""
    routes: dict[str, str] = {
        "add_new_expenses": "add_new_expenses_agent",
        "continue_pending_expense": "resolve_pending_expenses_agent",
        "view_expenses_report": "report_agent",
        "add_categories_recurring_expenses": "add_recurring_expenses_agent",
        "greeting": "greeting_agent",
        "undefined": "undefined_agent",
    }

    return routes.get(state.get("intention", "undefined"), "undefined_agent")


def route_after_pending_expiration(
    state: GraphState,
) -> Literal[
    "llm_call_router",
    "resolve_pending_expenses_agent",
    "resolve_pending_recurring_expenses_agent",
]:
    """Evita que o roteador descarte o contexto de uma pendência ativa.

    Pendência de gasto pontual tem precedência sobre a de gasto fixo: é o fluxo
    de maior frequência, e resolvê-lo primeiro minimiza o tempo médio com uma
    pergunta em aberto.
    """
    if state.get("pending_expenses") or state.get("expired_pending_expenses"):
        return "resolve_pending_expenses_agent"
    if state.get("pending_recurring_expenses") or state.get(
        "expired_pending_recurring_expenses"
    ):
        return "resolve_pending_recurring_expenses_agent"
    return "llm_call_router"


def route_after_pending_resolution(
    state: GraphState,
) -> Literal["add_new_expenses_agent", "finalize_response"]:
    """Permite gasto novo sem apagar o rascunho pendente."""
    return state.get("pending_expense_resolution_route", "finalize_response")


def route_after_pending_recurring_resolution(
    state: GraphState,
) -> Literal["add_recurring_expenses_agent", "finalize_response"]:
    """Permite cadastrar uma regra nova sem apagar o rascunho pendente."""
    return state.get("pending_recurring_expense_resolution_route", "finalize_response")


def route_input_content(
    state: GraphState,
) -> Literal["blocked_input", "ensure_user_node"]:
    """Decide o primeiro nó sem chamar o LLM."""
    if ensure_input_content_safe(state) == "unsafe":
        return "blocked_input"
    return "ensure_user_node"


async def blocked_input(state: GraphState) -> dict:
    """Encerra uma entrada bloqueada com uma resposta fixa, sem usar LLM."""
    return {"messages": [AIMessage(content=_UNSAFE_INPUT_MESSAGE)]}


async def greeting_agent(state: GraphState) -> dict:
    """Responde a cumprimentos sem intenção financeira."""
    return {"response_text": _GREETING}


async def expire_pending_expenses(state: GraphState) -> dict:
    """Remove rascunhos expirados antes de classificar a mensagem atual.

    Vale para os dois tipos de rascunho, com o mesmo TTL de 24 horas. As duas
    listas são separadas de propósito: um rascunho de gasto fixo entregue ao
    resolvedor de gasto pontual seria um objeto que ele não sabe tratar.
    """
    now = tools_calendar.user_now(state["user_timezone"])

    active, expired = split_expired_pending_expenses(
        list(state.get("pending_expenses", [])), now
    )
    active_recurring, expired_recurring = split_expired_pending_expenses(
        list(state.get("pending_recurring_expenses", [])), now
    )

    return {
        "pending_expenses": active,
        "expired_pending_expenses": expired,
        "pending_recurring_expenses": active_recurring,
        "expired_pending_recurring_expenses": expired_recurring,
        "needs_clarification": bool(active or active_recurring),
    }


async def undefined_agent(state: GraphState) -> dict:
    """Responde a mensagens fora do escopo do MVP."""
    return {"response_text": _NOT_IMPLEMENTED_YET}


async def report_agent(state: GraphState) -> dict:
    """Placeholder do agente de relatórios (ver ReAct/report_agent.py)."""
    return {"response_text": _NOT_IMPLEMENTED_YET}


def build_workflow() -> StateGraph:
    """Monta o grafo do assistente, sem compilar."""
    builder = StateGraph(GraphState, input_schema=InputState)

    builder.add_node("blocked_input", blocked_input)
    builder.add_node("ensure_user_node", ensure_user_node)
    builder.add_node("expire_pending_expenses", expire_pending_expenses)
    builder.add_node("llm_call_router", llm_call_router)
    builder.add_node("add_new_expenses_agent", add_new_expenses)
    builder.add_node("resolve_pending_expenses_agent", resolve_pending_expenses)
    builder.add_node("add_recurring_expenses_agent", add_recurring_expenses)
    builder.add_node(
        "resolve_pending_recurring_expenses_agent", resolve_pending_recurring_expenses
    )
    builder.add_node("report_agent", report_agent)
    builder.add_node("greeting_agent", greeting_agent)
    builder.add_node("undefined_agent", undefined_agent)
    builder.add_node("finalize_response", finalize_response)
    builder.add_node(
        "trim_messages", create_trim_node(keep_turns=settings.trim_keep_tuns_node)
    )

    builder.add_conditional_edges(
        START,
        route_input_content,
        ["blocked_input", "ensure_user_node"],
    )
    builder.add_edge("ensure_user_node", "expire_pending_expenses")
    builder.add_conditional_edges(
        "expire_pending_expenses",
        route_after_pending_expiration,
        [
            "llm_call_router",
            "resolve_pending_expenses_agent",
            "resolve_pending_recurring_expenses_agent",
        ],
    )
    builder.add_conditional_edges(
        "llm_call_router",
        route_decision_intentions,
        [
            "add_new_expenses_agent",
            "resolve_pending_expenses_agent",
            "report_agent",
            "add_recurring_expenses_agent",
            "greeting_agent",
            "undefined_agent",
        ],
    )

    builder.add_edge("blocked_input", END)

    builder.add_conditional_edges(
        "resolve_pending_expenses_agent",
        route_after_pending_resolution,
        ["add_new_expenses_agent", "finalize_response"],
    )

    builder.add_conditional_edges(
        "resolve_pending_recurring_expenses_agent",
        route_after_pending_recurring_resolution,
        ["add_recurring_expenses_agent", "finalize_response"],
    )

    for node in (
        "add_new_expenses_agent",
        "report_agent",
        "add_recurring_expenses_agent",
        "greeting_agent",
        "undefined_agent",
    ):
        builder.add_edge(node, "finalize_response")

    builder.add_edge("finalize_response", "trim_messages")
    builder.add_edge("trim_messages", END)

    return builder


async def graph():
    """Compila o grafo pronto para execução pelo worker."""

    async with open_checkpointer() as checkpointer:
        return build_workflow().compile(checkpointer=checkpointer)


if __name__ == "__main__":  # pragma: no cover - utilitário de inspeção manual
    import asyncio

    logger.debug(asyncio.run(graph()).get_graph().draw_mermaid())
