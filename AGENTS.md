# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project state

`docs/PRD.md` (in Portuguese) is the product/technical spec and remains the source of truth for anything not yet built — read the relevant PRD section before implementing a feature rather than guessing at intent. Where code already exists, the code wins.

What is implemented today:

- `db/migrations/001..004` — full schema: `message_queue`, `user`, `user_channel`, `category`, `recurring_expense`, `expense`, `expense_audit_log`, `model_usage`, plus `updated_at` triggers and Row-Level Security policies keyed on the `app.current_user_id` session variable.
- `src/shared/` — cross-cutting layer (see module mapping below): settings, LLM factory, prompt loader, global categories, async DB pool, repositories.
- `src/financial_agent/agent/` — LangGraph workflow (`build_graph_workflow.py`), state contracts (`state_graph.py`), deterministic tools (`tools/`), and the expense-registration sub-agent (`ReAct/add_new_expenses_agent.py`).
- `src/prompts_manager/` — separate uv workspace member: versioned prompt store with a Flask UI.

Still stubs: `server/` (FastAPI webhook), `worker/` (queue consumer), `scripts/`, `ReAct/report_agent.py`, and the categories/recurring-expenses agent. `build_graph_workflow.py` wires those last two as placeholder nodes that reply "em construção".

The Makefile's `.PHONY` line still lists targets that don't exist (`dev`, `db`, `api`, `worker`, `frontend`, `up`, `down`, `logs`, `clean`, `rag-phase-0`). Check the Makefile before relying on a target.

## Commands

```bash
make setup            # uv venv + install the project and prompts_manager as editable
make test             # pytest (DB-backed tests skip automatically when Postgres is down)
make check            # ruff check + ruff format --check + pyright src/
make fix && make format
make prompt-manager-serve   # Flask UI to author/version prompts
```

Notes:

- `pytest` gets `src/` on the path via `pythonpath = ["src"]` in `pyproject.toml`, so tests run without installing the package. Running a script directly still needs `PYTHONPATH=src` unless `make setup` was run.
- Tests marked `db` need a reachable Postgres with the migrations applied; run just those with `uv run pytest -m db`.
- `make sync-categories` is currently broken — it calls `financial_agent.shared.db_sync_categories.sync_categories_from_env`, but the module lives at `shared.db_sync_categories` and only exposes `sync_categories(conn)`.

## Prompts

Prompts are **not** hardcoded. `shared/prompt_loader.load_prompt_config(name)` reads the active version from `src/financial_agent/agent/prompts/metadata.json` and returns the whole config — `prompt_content`, `llm_model`, `llm_temperature`, `llm_reasoning_effort`. Never inline a system prompt in Python; register it through `prompts_manager` instead.

Drafts awaiting human review live in `docs/prompts/` and are not loaded by anything.

Registered so far: `ROUTER_SYSTEM_PROMPT` (v1.0.0). `ADD_EXPENSES_SYSTEM_PROMPT` is drafted in `docs/prompts/ADD_EXPENSES_SYSTEM_PROMPT_v1.0.0.md` but **not yet registered** — `add_new_expenses` raises `KeyError` until it is.

## Product context (from docs/PRD.md)

The product is a WhatsApp-first conversational assistant (Telegram is the dev/test channel) that lets users log expenses and ask about spending in natural language (Portuguese), e.g. "Gastei 35 reais no almoço." MVP phase, no bank integration — everything is user-reported via chat.

Key product rules that should constrain implementation choices:
- The LLM never computes financial totals itself — all aggregation/math happens in SQL/Postgres over structured data.
- Chat can only correct the **most recent** expense, and can never delete expenses or categories (those actions get a "not available yet, coming in the web UI" response).
- A single message can produce multiple expense records; ambiguous items are separated out for clarification while unambiguous ones in the same message are still saved.
- Money is stored as `NUMERIC`/decimal, never binary float.
- Every financial table carries a user id and every query must filter by it — this is the core multi-tenancy/isolation requirement (Row-Level Security is recommended where possible).
- Idempotency: each inbound message has a dedup key (channel + external message id + user id) so webhook/worker retries can't create duplicate expenses.
- Per-user message ordering must be preserved (e.g., "gastei 30 no almoço" then "na verdade foram 35" must apply in order) even though different users can be processed in parallel.
- Expense creation, LLM extraction, and audit logging are expected to carry cost/token/latency tracking per execution (see `model_usage`/`executions` tables in PRD §16).
- SLA: save+confirm an expense within 15s (P95); other responses within 25s.

## Intended architecture (from docs/PRD.md §15–18)

```
WhatsApp / Telegram → FastAPI webhook → persist message → Postgres-backed queue
  → workers (FOR UPDATE SKIP LOCKED, partitioned/ordered per user)
  → LangGraph agent graph → OpenRouter (LLM routing) + audio transcription service
  → domain services → Postgres → send confirmation back to the channel
```

- **FastAPI** only validates/normalizes webhooks, persists the raw message, enqueues a job, and returns immediately — it does not wait for agent processing to finish.
- **Postgres** is the system of record for users, messages, expenses, categories, recurring expenses, audit log, cost/usage tracking, *and* the job queue (no separate broker in the MVP). A Supabase MCP server is configured in `.Codex/settings.local.json`, suggesting Supabase is the intended Postgres host.
- **LangGraph** coordinates the per-message flow as a graph of agent nodes rather than separate services: load user context → transcribe audio → classify intent → extract expense(s) → validate → resolve ambiguity/ask for confirmation → persist → run report queries → manage categories/recurring expenses → generate response → send → record cost/metrics. The PRD's suggested `AssistantState` TypedDict (§15.4) is the reference shape for graph state.
- **OpenRouter** abstracts model access so cheap models can be used for intent classification and stronger models for extraction, with per-call cost/token logging.
- Actual module mapping (note: `shared/` is a **top-level package under `src/`**, not a subpackage of `financial_agent/`, despite what some older docstrings say):
  - `src/financial_agent/server/` — FastAPI app + webhook handlers (stub).
  - `src/financial_agent/worker/` — queue consumer/job runner (stub).
  - `src/financial_agent/agent/` — LangGraph graph, state contracts, nodes, and the `ReAct/` sub-agents.
  - `src/financial_agent/agent/tools/` — deterministic helpers (amount parsing, date resolution, payment-method normalization, category resolution). These are **plain Python functions, not LLM tool-calls** — keeping money math and category resolution out of the model is what enforces the PRD rules above.
  - `src/shared/` — settings (`config.py`), LLM factory (`llm.py`), prompt loader (`prompt_loader.py`), global categories (`categories.py`), async DB pool (`db.py`), and `repositories/` (one module per table: `users`, `categories`, `expenses`).
  - `src/financial_agent/scripts/` — one-off/maintenance scripts (stub).
- Database access is **async only** (`psycopg_pool.AsyncConnectionPool`). Go through `shared.db.user_connection(user_id)` for anything touching a financial table — it sets `app.current_user_id` for the transaction, which is what the RLS policies read. `shared.db.connection()` exists only for lookups that happen before the user is identified.
- Caveat worth knowing: RLS does not apply to a table's owner. If the app connects as the role that ran the migrations, the policies are bypassed and only the explicit `WHERE user_id = ...` filters in the repositories protect isolation.
- API and worker are meant to share one codebase but run as separate processes/containers (Docker-based deployment, per PRD §15.6).

## Skills

`.Codex/skills/` (mirrored under `.agents/skills/`) contains pinned copies tracked by `skills-lock.json`: `improve-codebase-architecture`, `requesting-code-review`, `security-review`. These are synced from external repos — don't hand-edit the skill files directly; update via whatever synced `skills-lock.json` instead.

## Task Master AI Instructions
**Import Task Master's development workflow commands and guidelines, treat as if import is in the main AGENTS.md file.**
@./.taskmaster/AGENTS.md
