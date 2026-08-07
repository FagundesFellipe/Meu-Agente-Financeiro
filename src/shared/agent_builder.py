"""Builder genérico de agentes LangChain com cache por versão de prompt.

Cada agente do sistema segue o mesmo padrão: carregar a config do prompt
ativo, instanciar um ``ChatOpenAI`` com os parâmetros da config e montar
um ``create_agent`` com o ``response_format`` estruturado apropriado.

Este módulo extrai esse boilerplate para que novos agentes só precisem
informar ``prompt_name``, ``version`` e ``response_format``.

Cache: a criação do ``ChatOpenAI`` + carregamento do prompt é cacheada por
``(prompt_name, version)`` — ambos strings hashable. O ``prompts_manager``
sempre cria uma nova versão ao alterar qualquer parâmetro (texto, modelo,
temperatura), então a string de versão é uma chave confiável. O ``create_agent``
final não é cacheado (custo desprezível) e aceita parâmetros não-hashable
como ``ToolStrategy``.
"""

from functools import lru_cache
from typing import Any

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel

from shared.llm import create_chat_model, get_model_id
from shared.prompt_loader import load_prompt_config


@lru_cache(maxsize=4)
def _get_llm_and_prompt(
    prompt_name: str,
    version: str,
) -> tuple[BaseChatModel, str]:
    """Carrega config do prompt e cria ChatOpenAI — cacheado por versão.

    Apenas parâmetros hashable (strings) compõem a chave do cache.
    """
    config = load_prompt_config(prompt_name)

    llm = create_chat_model(
        model=get_model_id(config["llm_model"]),
        temperature=config.get("llm_temperature"),
        reasoning_effort=config.get("llm_reasoning_effort"),
    )

    return llm, config["prompt_content"]


def build_agent_for_version(
    prompt_name: str,
    version: str,
    response_format: ToolStrategy,
    tools: list | None = None,
    agent_name: str = "",
) -> Any:
    """Constrói um agente com cache seletivo na parte custosa.

    O ``ChatOpenAI`` e o ``system_prompt`` são cacheados por
    ``(prompt_name, version)``. O ``create_agent`` é chamado a cada
    invocação — custo desprezível, e aceita ``response_format`` não-hashable.

    Args:
        prompt_name: Nome do prompt registrado no metadata
            (ex: ``"ADD_EXPENSES_SYSTEM_PROMPT"``).
        version: String da versão ativa, obtida via
            :func:`shared.prompt_loader.get_active_version`.
        response_format: Estratégia de resposta estruturada
            (ex: ``ToolStrategy(AddExpensesResult)``).
        tools: Lista de tools do agente. Default: ``[]``.
        agent_name: Nome do agente. Default: ``""``.

    Returns:
        Agente LangChain construído e pronto para uso.
    """
    llm, system_prompt = _get_llm_and_prompt(prompt_name, version)

    return create_agent(
        model=llm,
        tools=tools or [],
        system_prompt=system_prompt,
        response_format=response_format,
        name=agent_name,
    )
