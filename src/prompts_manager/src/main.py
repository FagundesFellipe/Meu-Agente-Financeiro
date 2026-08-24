import os
import sys

import structlog

from prompts_manager.config import settings
from prompts_manager.src.frontend.app import create_app

logger = structlog.get_logger()


def main() -> None:
    if settings.flask_debug and settings.environment_prompt_manager == "production":
        raise RuntimeError("FLASK_DEBUG não pode ser True em produção")

    prompt_dir = os.environ.get("PROMPT_DIR", settings.prompt_dir)

    if not prompt_dir:
        logger.error("PROMPT_DIR não está definido.")
        logger.error(
            "Adicione ao arquivo .env: PROMPT_DIR=/caminho/para/prompts "
            "ou exporte a variável: export PROMPT_DIR=/caminho/para/prompts"
        )
        sys.exit(1)

    logger.info("Prompt directory definido", prompt_dir=prompt_dir)
    logger.info("Iniciando servidor", url="http://127.0.0.1:5000")

    app = create_app()
    app.run(
        debug=settings.flask_debug, port=settings.prompt_manager_port, host="127.0.0.1"
    )


if __name__ == "__main__":
    main()
