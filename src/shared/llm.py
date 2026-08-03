"""
Fábrica de criação do modelo LLM com limitador de velocidade.

Centraliza a criação do ChatOpenAI com InMemoryRateLimiter do LangChain.
Todos os pontos que criam modelos devem usar esta fábrica para garantir
controle uniforme de custos.

Uso:
    from financial_agent.shared.llm import create_chat_model, ModelId

    model = create_chat_model()   # padrão
    model = create_chat_model(model=ModelId.GPT_4O_MINI)
    model = create_chat_model(temperature=0.0)   # determinístico
"""

from enum import StrEnum

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from shared.config import settings


class ModelId(StrEnum):
    """Catálogo fixo de IDs de modelos do OpenRouter.

    Cada membro é uma str com o ID completo no formato provider/modelo.
    Use diretamente no parâmetro ``model`` de ``create_chat_model``.

    Exemplo:
        router = create_chat_model(
            model=ModelId.GEMINI_2_5_FLASH_LITE,
        ).with_structured_output(RouteIntention)
    """

    # --- OpenAI ---
    GPT_5_4_NANO = "openai/gpt-5.4-nano"
    GPT_5_4_MINI = "openai/gpt-5.4-mini"
    GPT_5_4 = "openai/gpt-5.4"

    # --- Google ---
    GEMINI_2_5_FLASH_LITE = "google/gemini-2.5-flash-lite"
    GEMINI_2_5_FLASH = "google/gemini-2.5-flash"

    # --- DeepSeek ---
    DEEPSEEK_V4_FLASH = "deepseek/deepseek-v4-flash"


def get_model_id(identifier: ModelId | str) -> str:
    """Retorna o ID completo do modelo no formato provider/modelo.

    Aceita tanto o nome do membro do :class:`ModelId` quanto um ID completo.
    Se o valor já contiver ``/``, é retornado como está (pass-through).

    Args:
        identifier: Nome do membro (ex: ``"GPT_5_4_NANO"``) ou ID completo
                    (ex: ``"openai/gpt-5.4-nano"``).

    Returns:
        ID completo no formato ``provider/modelo``.

    Raises:
        ValueError: Se o identificador não for encontrado no catálogo.
    """
    if isinstance(identifier, ModelId):
        return identifier.value

    if "/" in identifier:
        return identifier

    try:
        return ModelId[identifier].value
    except KeyError:
        raise ValueError(
            f"Modelo '{identifier}' não encontrado no catálogo. "
            f"Use um ID completo (provider/modelo) ou um dos nomes: "
            f"{[m.name for m in ModelId]}"
        )


_RATE_LIMITERS: dict[tuple[float, int], InMemoryRateLimiter] = {}


def _get_rate_limiter(
    requests_per_second: float, max_bucket_size: int
) -> InMemoryRateLimiter:
    """Retorna limiter compartilhado por configuração.

    Reusa a mesma instância entre modelos com os mesmos parâmetros para que
    o bucket represente o throughput real do processo (e não de uma chamada).
    """

    key = (requests_per_second, max_bucket_size)
    if key not in _RATE_LIMITERS:
        _RATE_LIMITERS[key] = InMemoryRateLimiter(
            requests_per_second=requests_per_second, max_bucket_size=max_bucket_size
        )

    return _RATE_LIMITERS[key]


def create_chat_model(
    model: str | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
) -> ChatOpenAI:
    """Cria ChatOpenAI configurado com rate limiter.

    O rate limiter usa token bucket: limita requisições por segundo
    com burst para picos controlados. Valores vêm de settings
    (LLM_RATE_LIMIT_REQUESTS_PER_SECOND e LLM_RATE_LIMIT_MAX_BURST).

    Args:
        model: Nome do modelo. Default: settings.openrouter_model.
        temperature: Temperatura. Default: None (usa default do provider).
        reasoning_effort: Nível de raciocionio. Default None (usa default do provedor)

    Returns:
        ChatOpenAI com rate limiter aplicado.
    """

    api_key = settings.openrouter_api_key
    secrect_key = SecretStr(api_key.get_secret_value()) if api_key else None

    rate_limiter = _get_rate_limiter(
        requests_per_second=settings.llm_rate_limit_requests_per_second,
        max_bucket_size=settings.llm_rate_limit_max_burst,
    )

    kwargs: dict = {
        "model": model or settings.openrouter_midia_model,
        "api_key": secrect_key,
        "base_url": settings.openrouter_base_url,
        "rate_limiter": rate_limiter,
    }

    if temperature is not None:
        kwargs["temperature"] = temperature

    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort

    return ChatOpenAI(**kwargs)
