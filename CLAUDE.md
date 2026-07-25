# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This repository is pre-implementation. The only substantial artifact right now is `docs/PRD.md` (in Portuguese) — a full product/technical spec for a conversational expense-tracking assistant. All Python modules under `src/financial_agent/` are empty stub packages (`agent/`, `server/`, `worker/`, `scripts/`, `shared/`), `pyproject.toml` has no dependencies declared yet, and `tests/` (including `tests/integrations/`) has no tests. Treat the PRD as the source of truth for requirements and architecture until code exists to override it — always read the relevant PRD section before implementing a feature rather than guessing at intent.

The Makefile's `.PHONY` line lists many targets (`dev`, `db`, `api`, `worker`, `frontend`, `up`, `down`, `logs`, `lint`, `format`, `format-check`, `fix`, `typecheck`, `check`, `ci`, `test`, `test-x`, `test-v`, `clean`, `rag-phase-0`) but only `setup` is actually implemented. Don't assume any other `make` target works — check the Makefile before relying on one, and implement missing targets as the corresponding tooling is added.

## Commands

```bash
make setup   # uv venv && uv pip install -e ".[dev]"
```

No `[dev]` extra, lint config, type-check config, or test runner is wired up yet in `pyproject.toml`. When adding the first real dependencies/tooling, wire the matching Makefile target (`lint`, `format`, `typecheck`, `test`, etc.) at the same time so the `.PHONY` declarations stop being aspirational.

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
- **Postgres** is the system of record for users, messages, expenses, categories, recurring expenses, audit log, cost/usage tracking, *and* the job queue (no separate broker in the MVP). A Supabase MCP server is configured in `.claude/settings.local.json`, suggesting Supabase is the intended Postgres host.
- **LangGraph** coordinates the per-message flow as a graph of agent nodes rather than separate services: load user context → transcribe audio → classify intent → extract expense(s) → validate → resolve ambiguity/ask for confirmation → persist → run report queries → manage categories/recurring expenses → generate response → send → record cost/metrics. The PRD's suggested `AssistantState` TypedDict (§15.4) is the reference shape for graph state.
- **OpenRouter** abstracts model access so cheap models can be used for intent classification and stronger models for extraction, with per-call cost/token logging.
- Expected module mapping onto `src/financial_agent/`: `server/` = FastAPI app + webhook handlers, `worker/` = queue consumer/job runner, `agent/` = LangGraph graph and node implementations, `shared/` = cross-cutting models/utilities (db access, cost tracking, idempotency), `scripts/` = one-off/maintenance scripts. Confirm this mapping against actual code as modules are filled in — it's inferred from the PRD, not yet established by the codebase.
- API and worker are meant to share one codebase but run as separate processes/containers (Docker-based deployment, per PRD §15.6).

## Skills

`.claude/skills/` (mirrored under `.agents/skills/`) contains pinned copies tracked by `skills-lock.json`: `improve-codebase-architecture`, `requesting-code-review`, `security-review`. These are synced from external repos — don't hand-edit the skill files directly; update via whatever synced `skills-lock.json` instead.

## Task Master AI Instructions
**Import Task Master's development workflow commands and guidelines, treat as if import is in the main CLAUDE.md file.**
@./.taskmaster/CLAUDE.md
