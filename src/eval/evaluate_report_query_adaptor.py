"""Adaptador de avaliação para a extração pura de consultas de relatório."""

from datetime import datetime
from typing import cast
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage

from financial_agent.agent.ReAct.report_agent import build_report_query_agent
from financial_agent.agent.state_graph import ExpenseQuery
from shared.categories import GLOBAL_CATEGORIES
from shared.repositories.categories import (
    CategoryRecord,
    format_categories_for_prompt,
)

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
    content = "\n".join(
        [
            "# CONTEXTO",
            f"DATA_HORA_ATUAL: {_EVALUATION_REFERENCE_DATETIME.isoformat()}",
            "INICIO_DA_SEMANA: segunda-feira",
            "",
            "CATEGORIAS_DISPONIVEIS:",
            format_categories_for_prompt(categories),
        ]
    )
    return SystemMessage(content=content)


async def evaluate_report_query_extraction(user_message_text: str) -> str:
    """Executa somente a extração da LLM e serializa sua resposta estruturada."""
    agent = build_report_query_agent()
    result = await agent.ainvoke(
        {
            "messages": [
                build_evaluation_context(),
                HumanMessage(content=user_message_text),
            ]
        }
    )
    structured_response = cast(ExpenseQuery, result["structured_response"])
    return structured_response.model_dump_json()
