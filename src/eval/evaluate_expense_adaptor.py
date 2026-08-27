"""Adaptador de avaliação para a extração pura de despesas."""

from datetime import datetime
from typing import cast
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from langchain.messages import HumanMessage
from langchain_core.messages import SystemMessage

from financial_agent.agent.ReAct.add_new_expenses_agent import (
    build_add_expenses_agent,
    build_context_message,
)
from financial_agent.agent.state_graph import AddExpensesResult
from shared.categories import GLOBAL_CATEGORIES
from shared.repositories.categories import CategoryRecord

_EVALUATION_REFERENCE_DATETIME = datetime(
    2026, 8, 26, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo")
)


def build_evaluation_context() -> SystemMessage:
    """Cria o contexto estável usado por todos os casos do golden dataset."""
    categories = [
        CategoryRecord(
            id=uuid5(NAMESPACE_URL, f"evaluation-category:{category.normalized_name}"),
            name=category.name,
            normalized_name=category.normalized_name,
            description=category.description,
            is_personal=False,
        )
        for category in GLOBAL_CATEGORIES
    ]
    return build_context_message(_EVALUATION_REFERENCE_DATETIME, categories)


async def evaluate_expense_exctraction(user_message_text: str) -> str:
    """Executa somente a extração da LLM e serializa sua resposta estruturada."""
    agent = build_add_expenses_agent()
    result = await agent.ainvoke(
        {
            "messages": [
                build_evaluation_context(),
                HumanMessage(content=user_message_text),
            ]
        }
    )
    structured_response = cast(AddExpensesResult, result["structured_response"])
    return structured_response.model_dump_json()
