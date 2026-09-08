# Development Workflow

This file is the mandatory execution playbook for every coding task in this
repository. Read it at the start of each session and keep it as the operating
reference until the task is closed.

The workflow exists to make professional habits explicit: protect existing
work, implement against an agreed specification and plan, keep architectural
decisions human-approved, validate independently, and leave an auditable
record for the next session.

## Core Rules

- Follow this workflow in order. Do not skip a step because the task appears
  small.
- Do not push to any remote repository. A commit is the furthest Git write
  allowed by this workflow.
- Never commit without the user's explicit approval of the exact proposed
  commit message.
- Preserve unrelated user changes. Do not reset, restore, discard, amend, or
  rewrite work that was already in the working tree.
- Treat the user as the human in the loop. Ask before making an architectural
  decision that could change existing behavior, interfaces, data models,
  dependencies, module boundaries, or implementation patterns.
- Do not invent requirements. The provided specification and implementation
  plan define the task scope.
- Report facts separately from assumptions. State what was inspected and what
  was actually run.

## 1. Session Preflight and Git Safety

Before reading or changing application code:

1. Inspect the repository state with `git status --short`, including both
   staged and unstaged changes.
2. If files are modified, added, deleted, or staged but not committed:
   - inspect their diff and identify whether they relate to the requested task;
   - preserve unrelated work exactly as found;
   - write a clear proposed commit message for the existing changes and ask the
     user to approve that message;
   - wait for explicit approval before committing;
   - after approval, create only that commit; never push it.
3. If the user does not approve the proposed message, do not commit. Continue
   only when their direction makes the intended working-tree state clear.
4. Create a task-specific branch before implementation, using the repository
   convention. Ask the user before
   branching if an existing branch, uncommitted work, or task convention makes
   the correct base or branch name unclear.

## 2. Load Mandatory Context

Before implementation, load and follow these sources in this order:

1. Repository instructions such as `AGENTS.md`, `CLAUDE.md` `RTK.md`, and any applicable
   nested instructions.
2. The Clean Code skill from `.agents/skills/clean-code` (or its configured
   equivalent). Use it both while designing the change and in the final
   self-review.
3. The task specification supplied by the user from `/spec`.
4. The implementation plan supplied by the user.
5. Relevant existing code, tests, contracts, migrations, and documentation.

If the specification or plan is missing, ambiguous, inconsistent with the
current code, or requires a material architectural choice, stop and ask the
user a concise question before modifying code. Do not replace that decision
with an assumption.

## 3. Implement Within the Agreed Plan

1. Implement only the agreed scope, applying the Clean Code skill throughout.
2. Prefer small, cohesive changes that match the repository's established
   patterns.
3. Add or update tests required by the specification and implementation plan.
4. Keep the project rules intact: do not bypass validation, authorization,
   tenant isolation, idempotency, money precision, or established error
   contracts.
5. If a new uncertainty or architectural decision appears during execution,
   pause and ask the user. Do not silently choose a direction.
6. Do not make opportunistic refactors or unrelated corrections. Record them
   as observations for the final report instead.

## 4. Validate the Implemented Scope

After implementation, validate proportionally to the change:

1. Run the relevant focused tests, then the broader prescribed checks when
   feasible.
2. Run formatting, linting, type checking, and any project-required checks. Use make commands
3. Inspect the final diff to confirm that it matches the agreed specification
   and implementation plan and contains no unrelated change.
4. Clearly distinguish passing checks, skipped checks, and checks that could
   not run, including the reason.

## 5. Record Project Memory

Before closing the task, use Basic Memory MCP to persist an accurate, concise
record of:

- every architectural decision approved and implemented;
- every change to existing code, including affected files and behavior;
- every new implementation, including purpose and integration point;
- tests and checks executed, with outcomes and any limitations;
- unresolved review or security findings that need future follow-up.

Do not save secrets, tokens, credentials, personally identifiable information,
or speculative claims. The record must let a future agent understand the
decision and avoid rediscovering it from scratch.

.

## 6. Independent Review Gate

Do not correct code after this gate unless the user explicitly starts a new
implementation or correction task. This gate produces findings and a report;
it does not authorize further edits.

1. Re-load the Clean Code skill and review the final implementation for any
   missed applicable principle.
2. Use a second, independent LLM reviewer through multi-agent review. Ask it
   to assess the agreed scope, correctness, tests, and Clean Code application.
3. Use the `requesting-code-review` skill for a structured code review.
4. Use the `security-review` skill to assess security implications of the
   changed code and its data flow.
5. Do not fix review findings in this phase. Include each finding, severity,
   evidence, and recommended next action in the final report for the user to
   decide.
### 6.1. Close With a Portuguese Report

After the memory record is saved, provide a final report in Brazilian
Portuguese. Do not make additional code corrections at this point.

The report must include:

- what was implemented, mapped to the specification and plan;
- files added or changed and the practical reason for each;
- architectural decisions approved by the user;
- validation commands and their pass/fail/skip results;
- Clean Code, independent-review, code-review, and security-review results;
- limitations, unrun checks, and any findings that require a separate task;
- Git status and whether a commit was proposed, approved, created, or not
  created.

Use direct, evidence-based language. Never claim a test, review, commit, push,
or memory update happened unless it actually happened


