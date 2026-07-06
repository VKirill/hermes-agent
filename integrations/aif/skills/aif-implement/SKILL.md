---
name: aif-implement
description: >-
  Execute implementation tasks from a plan (or a single scoped task) one at a time,
  with verbose configurable logging, per-task verification, and progress tracking.
  Use when a dev task is ready to code, or the user says "implement", "start coding",
  "execute plan", "continue implementation". This is the aif_implementer role skill
  (port of lee-to AI Factory /aif-implement, adapted to Hermes).
tags:
  - aif
  - implementation
  - dev-factory
  - kanban
---

# aif-implement — Execute the plan

Implement scoped changes from an approved kanban task/plan, return real evidence, keep changes minimal and reversible.

## Hermes context

- You run **as a kanban worker** under `aif_implementer`. Native kanban is the handoff layer — **no `HANDOFF_MODE`, no MCP, no `.ai-factory/config.yaml`**. Artifacts under **`.hermes-dev/`**.
- **Autonomous:** no interactive questions. If context/access is missing or a change is irreversible/prod-affecting (deploy/publish/migrate/spend/force-push/merge), **block** with the exact reason. Otherwise implement and complete.

## Step 0 — Load context & plan

Read if present: `DESCRIPTION.md` and `ARCHITECTURE.md` at the project root, `.hermes-dev/RULES.md` (+ `rules/*`), and **`.hermes-dev/skill-context/aif-implement/SKILL.md` (MANDATORY if it exists** — project rules from `/aif-evolve`; skill-context wins on conflict). Then read the kanban task body + parent handoffs and the plan at `.hermes-dev/plans/<slug>.md`. Inspect existing code before editing — never invent architecture from memory.

## Step 1–3 — Execute ONE task at a time

For each task in the plan (respect dependency order):
1. **Implement** the target task with direct tool calls. Follow existing code patterns and `ARCHITECTURE.md` boundaries. Implement only the requested scope.
2. **Add verbose, configurable logging** — function entry/exit, state changes, external calls, error context. Structured logs, level via env (e.g. `LOG_LEVEL`). Do NOT skip logging "to keep code clean" — it is required, but must be configurable.
3. **Verify the change** — compiles/runs, described behavior works, fix immediate issues.
4. **Mark progress** — flip the plan checkbox `- [ ]` → `- [x]` immediately after each task (plan file is the source of truth for progress).
5. **Commit checkpoint** — if the plan defines one and you're at it, commit with the suggested conventional message (only if committing is in scope for this workspace).

Handle exactly ONE task (or one tightly-coupled group) per cycle; do not silently expand scope.

## Completion — return evidence & hand off

**Commit before handing off (workflow cards — mandatory):** the card moves to another role's
session next; uncommitted work makes the review diff unreadable and the worktree unmergeable.
`git add` your changes and commit per `aif-commit` discipline (conventional message; NEVER push).
Skip only when the workspace has no git repo.

Return a structured handoff: changed files, commands/tests run and their outcomes, workspace path, remaining non-blocking warnings. Then **complete the kanban task on evidence** (green checks → `kanban_complete`; do not self-block waiting for human approval). The `aif_verifier` and `aif_reviewer` gates catch quality issues downstream — that is their job, not yours.

## DO
- ✅ One task at a time; mark in-progress → completed.
- ✅ Follow existing conventions + `/aif-best-practices` (naming, structure, error handling).
- ✅ Create files named in the task; handle stated edge cases.
- ✅ Add verbose configurable logging to all code.

## DON'T
- ❌ Write tests unless the task list explicitly includes test tasks.
- ❌ Create report/summary documents after completion.
- ❌ Add tasks not in the plan; skip planned tasks; mark incomplete work done.
- ❌ Violate `ARCHITECTURE.md` file placement / module boundaries.
- ❌ Self-block with "needs human approval" when checks are green (that dams the pipeline).

## Critical rules
1. NEVER write tests unless planned. 2. NEVER create reports. 3. ALWAYS update the plan checkbox right after each task. 4. Preserve progress across sessions. 5. ONE task at a time. 6. Verbose configurable logging always. 7. Block only on real failure / missing context / irreversible action.

## References

- `references/IMPLEMENTATION-GUIDE.md` — progress display format, blocker handling (block-not-ask), plan discovery order, session recovery after a break.
- `references/LOGGING-GUIDE.md` — the verbose-but-configurable logging requirements with code patterns (why, what, and how to gate by `LOG_LEVEL`).
- `tests/*.yaml` — spec-style fixtures documenting expected behavior (ported from lee-to; no Hermes runner consumes them yet).
