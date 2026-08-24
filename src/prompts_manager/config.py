"""
Configuração centralizada via variáveis de ambiente.
"""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_prompts_dir() -> Path:
    """Resolve o diretório de prompts para dev local, pacote instalado e Docker"""

    candidates = [
        Path(__file__).resolve().parent.parent / "financial_agent/agent/prompts",
        Path("/app/src/financial_agent/agent/prompts"),
        Path.cwd() / "src/financial_agent/agent/prompts",
    ]

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    return candidates[0]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- Environment ----
    # "development" (default) ou "production"
    # Em produção, o webhook sincrono (webhook/sync) é desabilitado
    environment_prompt_manager: str = "development"

    # --- Diretórios dos Prompts
    prompt_dir: str = str(_resolve_prompts_dir())

    # --- Limite de tamanho do prompt
    max_prompt_size: int = 100_000

    # --- Frontend
    prompt_manager_port: int = 5000
    flask_secret_key: SecretStr | None = None
    flask_debug: bool = False

    # --- Timezone
    prompt_manager_server_timezone: str = "UTC"


settings = Settings()
