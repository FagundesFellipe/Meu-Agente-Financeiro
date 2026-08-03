import os
import sys

from prompts_manager.config import settings
from prompts_manager.src.frontend.app import create_app


def main() -> None:
    prompt_dir = os.environ.get("PROMPT_DIR", settings.prompt_dir)

    if not prompt_dir:
        print("❌ Erro: PROMPT_DIR não está definido.")
        print()
        print("   Adicione ao arquivo .env:")
        print("     PROMPT_DIR=/caminho/para/prompts")
        print()
        print("   Ou exporte a variável:")
        print("     export PROMPT_DIR=/caminho/para/prompts")
        print()
        sys.exit(1)

    print(f"📂 Prompt directory: {prompt_dir}")
    print("🚀 Iniciando servidor em http://127.0.0.1:5000")

    app = create_app()
    app.run(
        debug=settings.flask_debug, port=settings.prompt_manager_port, host="127.0.0.1"
    )


if __name__ == "__main__":
    main()
