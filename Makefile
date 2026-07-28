-include .env
.PHONY: help dev setup db api worker frontend up down logs lint format format-check fix typecheck check ci test test-x test-v clean rag-phase-0

# Cores para output
CYAN := \033[36m
RESET := \033[0m

PY := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else command -v python; fi)

##@ Geral
help: ## Mostra esta mensagem de ajuda
	@awk 'BEGIN {FS = ":.*##"; printf "\nUso:\n  make $(CYAN)<comando>$(RESET)\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  $(CYAN)%-15s$(RESET) %s\n", $$1, $$2 } /^##@/ { printf "\n%s\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Setup
setup: ## Cria .venv e instala dependências
	uv venv
	uv pip install -e ".[dev]"


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