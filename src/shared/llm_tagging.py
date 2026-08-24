"""Marca cada chamada LLM à OpenRouter com o agente e o usuário de origem.

A OpenRouter já expõe um dashboard de custo/tokens/latência por chamada
(Activity/Generations). O único dado que falta lá é *qual agente interno*
disparou a chamada — a coluna "App" aparece como "Unknown" porque nada
identifica a origem. Este módulo resolve só isso, via ``user`` (campo
OpenAI-compatible padrão, por requisição, que a OpenRouter expõe de volta
como ``external_user`` em ``GET /generation``).

Não grava nada no banco — é só marcação da requisição enviada à OpenRouter.
"""

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import (
    AgentMiddleware,
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage


class OpenRouterTaggingMiddleware(AgentMiddleware):
    """Injeta ``user`` (e ``X-Title``, best-effort) em cada chamada ao modelo.

    O ``ChatOpenAI`` é cacheado e compartilhado entre usuários diferentes
    (``shared.agent_builder._get_llm_and_prompt``), então o ``user_id`` não
    pode ser amarrado na construção do modelo — precisa entrar por chamada,
    aqui, a partir do ``state`` do grafo.
    """

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse | AIMessage | ExtendedModelResponse:
        user_id = request.state.get("user_id")
        tag = f"{user_id}:{self.agent_name}" if user_id else self.agent_name

        request.model_settings = {
            **request.model_settings,
            "extra_body": {"user": tag},
            "extra_headers": {"X-Title": self.agent_name},
        }
        return await handler(request)
