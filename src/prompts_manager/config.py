"""
Centralized configuration via environment variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Diretórios dos Prompts
    prompt_dir: str = "/src/financial_agent/agent/prompts"

    # --- Limite de tamanho do prompt
    max_prompt_size: int = 100_000

    # --- Frontend
    prompt_manager_port: int = 5000
    flask_secret_key: str = "prompt-manager-dev-key"
    flask_debug: bool = False


settings = Settings()
