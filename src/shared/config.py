"""
Configuração centralizada via variáveis de ambiente.

Usa pydantic-settings para carregar, validar e tipar todas as configurações
do projeto a partir de variáveis de ambiente ou arquivo .env.

Uso:
    from financial_agent.shared.config import settings

    print(settings.database_url)
    print(settings.rate_limit_per_hour)

Todas as configurações possuem valores padrão sensatos para desenvolvimento local.
Em produção, configure via variáveis de ambiente ou .env.
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM (OpenRouter) ---
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "google/gemini-2.5-flash-lite"
    openrouter_midia_model: str = "google/gemini-2.5-flash-lite"

    # --- DATABASE
    database_url: str = (
        "postgresql://postgres:postgres@localhost:5433/meu_agente_financeiro"
    )

    # --- LLM Rate Limit ---
    llm_rate_limit_requests_per_second: float = 0.5
    llm_rate_limit_max_burst: int = 10


settings = Settings()
