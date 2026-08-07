-include .env
.PHONY: help dev setup db api worker frontend up down logs lint format format-check fix typecheck check ci test test-x test-v test-s clean rag-phase-0 prompt-manager-serve sync-categories graph

# Cores para output
CYAN := \033[36m
GREEN := \033[32m
RED := \033[31m
RESET := \033[0m

PY := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else command -v python; fi)

##@ Geral
help: ## Mostra esta mensagem de ajuda
	@awk 'BEGIN {FS = ":.*##"; printf "\nUso:\n  make $(CYAN)<comando>$(RESET)\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2 } /^##@/ { printf "\n%s\n", substr($$0, 5) } ' $(MAKEFILE_LIST)


##@ Setup
setup: ## Cria .venv e instala dependências
	uv venv
	uv pip install -e ".[dev]"
	uv pip install -e "./src/prompts_manager"


##@ Desenvolvimento
dev: ## Inicia LangGraph Studio
	uv run langgraph dev

db: ## Inicia apenas o PostgresSQL
	docker compose up -d db		

migrations: ## Executa todas as migrações (DB)
	uv run python db/migrate.py

sync-categories: ## Sincroniza categorias globais (categories.py → PostgreSQL)
	uv run python -c "import asyncio; from src.shared.db_sync_categories import sync_categories; inserted = asyncio.run(sync_categories()); print(f'{inserted} categorias inseridas.')"


##@ Qualidade de Código
# Estes comandos verificam estilo e tipos, NÃO lógica.
# Para testar lógica, use: make test
#
# Fluxo típico:
#   make fix && make format   # Corrige e formata
#   make check                # Verifica se está tudo ok
#   git commit

lint: ## Encontra problemas (imports, sintaxe) — não altera arquivos
	uv run ruff check .

format: ## Formata código — ALTERA arquivos
	uv run ruff format .

format-check: ## Verifica se está formatado — não altera (para CI)
	uv run ruff format --check .

fix: ## Corrige problemas automaticamente — ALTERA arquivos
	uv run ruff check --fix .

typecheck: ## Verifica tipos estáticos (pyright) — não altera arquivos
	uv run pyright src/

check: ## Verifica tudo (lint + format + types) — não altera arquivos
	uv run ruff check . && uv run ruff format --check . && uv run pyright src/

ci: ## CI/CD: verifica tudo + roda testes — não altera arquivos
	uv run ruff check . && uv run ruff format --check . && uv run pyright src/ && uv run pytest

##@ Testes
test: ## Roda todos os testes
	uv run pytest

test-x: ## Roda testes, para no primeiro erro
	uv run pytest -x

test-v: ## Roda testes com output verboso
	uv run pytest -v

test-s: ##Roda testes com logs de print() adicionado
	uv run pytest -v -s


##@ Prompt Manager — Frontend
# Interface web (Flask + Tailwind CSS) para gerenciar prompts com versionamento semântico.
#
# Pré-requisito: a variável PROMPT_DIR deve estar definida no arquivo .env
# ou exportada no ambiente. Exemplo:
#
#   echo 'PROMPT_DIR=./data/prompts' >> .env
#
# Uso:
#   make prompt-manager-serve          # Inicia o servidor em http://127.0.0.1:5000

prompt-manager-serve: ## Inicia o servidor Flask do gerenciador de prompts
	uv run python -m prompts_manager.src.main


##@ Agente
graph: ## Imprime o grafo do agente em Mermaid (não executa nada)
	uv run python -m financial_agent.agent.build_graph_workflow

