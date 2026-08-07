"""Constrói o workflow LangGraph — nós, arestas e roteamento por intenção.

Este módulo só monta o grafo; nenhuma execução acontece na importação.
Para inspecionar o desenho ou fazer um teste manual, use ``make graph`` ou
``python -m financial_agent.agent.build_graph_workflow``.
"""

from typing import cast

import structlog
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from financial_agent.agent.ReAct.add_new_expenses_agent import add_new_expenses
from financial_agent.agent.state_graph import GraphState, InputState, Intentions
from shared.llm import create_chat_model, get_model_id
from shared.prompt_loader import load_prompt_config
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
    """Prefixa a boas-vindas na primeira resposta da vida do usuário."""
    response_text = state.get("response_text")
    if state.get("is_new_user") and response_text:
        return {"response_text": f"{_WELCOME_PREFIX}\n\n{response_text}"}
    return {"response_text": response_text}


async def llm_call_router(state: GraphState) -> dict:
    ROUTER_PROMPT_NAME = "ROUTER_SYSTEM_PROMPT"

    """Classifica a intenção da mensagem do usuário."""
    prompt_config = load_prompt_config(ROUTER_PROMPT_NAME)

    llm = create_chat_model(
        model=get_model_id(prompt_config["llm_model"]),
        temperature=prompt_config.get("llm_temperature"),
        reasoning_effort=prompt_config.get("llm_reasoning_effort"),
    ).with_structured_output(RouteIntention)

    result = cast(
        RouteIntention,
        await llm.ainvoke(
            [
                {"role": "system", "content": prompt_config["prompt_content"]},
                *state["messages"],
            ]
        ),
    )

    return {"intention": result.intentions_decision}


def route_decision(state: GraphState) -> str:
    """Escolhe o nó de destino a partir da intenção classificada."""
    routes: dict[str, str] = {
        "add_new_expenses": "add_new_expenses_agent",
        "view_expenses_report": "report_agent",
        "add_categories_recurring_expenses": "add_recurring_expenses_agent",
        "greeting": "greeting_agent",
        "undefined": "undefined_agent",
    }

    return routes.get(state.get("intention", "undefined"), "undefined_agent")


async def greeting_agent(state: GraphState) -> dict:
    """Responde a cumprimentos sem intenção financeira."""
    return {"response_text": _GREETING}


async def undefined_agent(state: GraphState) -> dict:
    """Responde a mensagens fora do escopo do MVP."""
    return {"response_text": _NOT_IMPLEMENTED_YET}


async def report_agent(state: GraphState) -> dict:
    """Placeholder do agente de relatórios (ver ReAct/report_agent.py)."""
    return {"response_text": _NOT_IMPLEMENTED_YET}


async def add_recurring_expenses_agent(state: GraphState) -> dict:
    """Placeholder do agente de categorias/gastos recorrentes."""
    return {"response_text": _NOT_IMPLEMENTED_YET}


def build_workflow() -> StateGraph:
    """Monta o grafo do assistente, sem compilar."""
    builder = StateGraph(GraphState, input_schema=InputState)

    builder.add_node("ensure_user_node", ensure_user_node)
    builder.add_node("llm_call_router", llm_call_router)
    builder.add_node("add_new_expenses_agent", add_new_expenses)
    builder.add_node("add_recurring_expenses_agent", add_recurring_expenses_agent)
    builder.add_node("report_agent", report_agent)
    builder.add_node("greeting_agent", greeting_agent)
    builder.add_node("undefined_agent", undefined_agent)
    builder.add_node("finalize_response", finalize_response)

    builder.add_edge(START, "ensure_user_node")
    builder.add_edge("ensure_user_node", "llm_call_router")
    builder.add_conditional_edges(
        "llm_call_router",
        route_decision,
        [
            "add_new_expenses_agent",
            "report_agent",
            "add_recurring_expenses_agent",
            "greeting_agent",
            "undefined_agent",
        ],
    )

    for node in (
        "add_new_expenses_agent",
        "report_agent",
        "add_recurring_expenses_agent",
        "greeting_agent",
        "undefined_agent",
    ):
        builder.add_edge(node, "finalize_response")

    builder.add_edge("finalize_response", END)

    return builder


def graph():
    """Compila o grafo pronto para execução pelo worker."""
    return build_workflow().compile()


if __name__ == "__main__":  # pragma: no cover - utilitário de inspeção manual
    logger.debug(graph().get_graph().draw_mermaid())
