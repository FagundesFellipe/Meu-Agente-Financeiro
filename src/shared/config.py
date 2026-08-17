"""
Configuração centralizada via variáveis de ambiente.

Usa pydantic-settings para carregar, validar e tipar todas as configurações
do projeto a partir de variáveis de ambiente ou arquivo .env.

Uso:
    from financial_agent.shared.config import settings


Todas as configurações possuem valores padrão sensatos para desenvolvimento local.
Em produção, configure via variáveis de ambiente ou .env.
"""

import logging
import os

import structlog
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _configure_structlog() -> None:
    """Configura formatação e nível de log do structlog.

    Em desenvolvimento local, usa formato colorido e legível.
    Em produção (``ENV=production``), usa JSON estruturado.
    """
    is_production = os.environ.get("ENVIRONMENT", "").lower() == "production"

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if is_production:
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
        )
    else:
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
        )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- ENVIRONMENT ---
    environment: str = "development"
    enable_sync_webhook: bool = False

    # --- LLM (OpenRouter) ---
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "google/gemini-2.5-flash-lite"
    openrouter_midia_model: str = "google/gemini-2.5-flash-lite"

    # --- DATABASE
    database_url: str = ""
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_pool_open_timeout: float = 10.0

    # --- AGENT ---
    agent_id: str = "finantial_agent"
    default_timezone: str = "America/Sao_Paulo"
    fallback_category_name: str = "Outros gastos"

    # --- LLM Rate Limit ---
    llm_rate_limit_requests_per_second: float = 0.5
    llm_rate_limit_max_burst: int = 10

    # --- DEBOUNCE ---
    message_buffer_seconds: float = 2.0

    # --- TRIM ---
    # Mantém os N turnos mais recentes, descarta os antigos.
    # Um turno = 1 HumanMessage + todas as respostas (AI, tools, etc).
    # Custo: zero (sem chamada LLM extra)
    trim_keep_tuns: int = 3
    trim_keep_tuns_node: int = 5

    # --- TELEGRAM ---
    telegram_bot_token: SecretStr | None = None
    telegram_webhook_secret_token: str | None = None

    # --- FASTAPI SERVER ---
    port: int = 8000
    cors_allowed_origins: str = "http://localhost:3000"

    @property
    def resolved_cors_allowed_origins(self) -> list[str]:
        """Lista de origins CORS, parseada da string separada por vírgula."""
        origins = self.cors_allowed_origins.split(",")
        return [origin.strip() for origin in origins if origin.strip()]


settings = Settings()
