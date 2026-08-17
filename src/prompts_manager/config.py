"""
Configuração centralizada via variáveis de ambiente.
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- Environment ----
    # "development" (default) ou "production"
    # Em produção, o webhook sincrono (webhook/sync) é desabilitado
    environment_prompt_manager: str = "development"

    # --- Diretórios dos Prompts
    prompt_dir: str = "/src/financial_agent/agent/prompts"

    # --- Limite de tamanho do prompt
    max_prompt_size: int = 100_000

    # --- Frontend
    prompt_manager_port: int = 5000
    flask_secret_key: SecretStr | None = None
    flask_debug: bool = False

    # --- Timezone
    prompt_manager_server_timezone: str = "UTC"


settings = Settings()
