---
name: aif-plan
description: >-
  Turn an approved kanban task / spec / brief into a concrete, implementation-ready
  development plan. Explore the codebase, write a checklist plan with acceptance checks
  and dependency order, and hand off to implementation. Use when a dev task needs planning
  before code changes, or when the user says "plan", "new feature", "break this down".
  This is the aif_planner role skill (port of lee-to AI Factory /aif-plan, adapted to Hermes).
tags:
  - aif
  - planning
  - dev-factory
  - kanban
  - spec-driven
---

# aif-plan — Implementation Planning

Produce a bounded, actionable plan a downstream worker can execute without drifting.

## Hermes context (how this differs from lee-to's original)

- You run **as a kanban worker** on the `departments` board under the `aif_planner` profile. The native Hermes kanban IS the handoff layer — there is **no `HANDOFF_MODE`, no MCP handoff, no `.ai-factory/config.yaml`**.
- Artifacts live under **`.hermes-dev/`** in the target workspace (`plans/`, `specs/`, `contracts/`, `rules/`, `skill-context/`), not `.ai-factory/`.
- **Autonomous mode:** you have no human at the keyboard. Do **not** use interactive questions. If input is genuinely missing or scope is unsafe, **block the kanban task** with a specific reason instead of guessing.

## Step 0 — Load project context

Read these if present in the target workspace before planning:
- `DESCRIPTION.md` (project root) — tech stack, conventions, non-functional reqs
- `ARCHITECTURE.md` (project root) — pattern, folder structure, layer/dependency rules
- `.hermes-dev/RULES.md` (+ `.hermes-dev/rules/*`) — hard project rules; these override general patterns
- `.hermes-dev/skill-context/aif-plan/SKILL.md` — **MANDATORY if it exists.** Project rules accumulated by `/aif-evolve`. On conflict, skill-context wins over this file. Verify every generated artifact against these rules before finishing.
- The kanban task body + parent handoffs (via `hermes kanban show <id>`).

## Step 1 — Reconnaissance

Understand the relevant slice of the codebase first. Prefer 1–2 `Explore` subagents (thoroughness: quick) if available; otherwise use `Glob`/`Grep`/`Read` directly. Never invent architecture from memory.

## Step 2 — Analyze requirements

Extract: core functionality, key domain terms, type (feature/enhancement/fix/refactor), components/files to touch, dependencies, edge cases. If requirements are ambiguous or context is missing — **block with the exact missing input**, do not fabricate scope.

## Step 3 — Explore codebase

Map: which files to create/modify, patterns to follow (from existing code), dependencies between components, risks/edge cases. Follow `ARCHITECTURE.md` for file placement and module boundaries.

## Step 3.5 — New-application bootstrap (own folder + project)

If this is a **new application** (the task body says "new app" / there is no existing repo/folder to work in), create a dedicated project and standardized workspace BEFORE writing tasks, so every app lands in its own folder:

1. Derive a slug from the app name — lowercase, hyphenated, ≤40 chars (e.g. "парсер цен X" → `parser-cen-x`).
2. Scaffold the folder + standardized `.hermes-dev/` and init git:
   ```
   mkdir -p ~/Work/apps/<slug>/.hermes-dev/{plans,specs,contracts,gates,rules,skill-context}
   git -C ~/Work/apps/<slug> init -q
   ```
3. Register the project (deterministic worktree + branch convention, board-bound):
   ```
   hermes project create "<App Name>" --slug <slug> --primary ~/Work/apps/<slug> --board departments
   ```
4. Anchor every implementation task to the project so workers operate in its folder:
   `hermes kanban --board departments create "<task>" --assignee aif_implementer --project <slug> ...`
   (or `--workspace dir:~/Work/apps/<slug>` for direct, no-worktree work on a fresh app).
5. Write the plan file (Step 5) into `~/Work/apps/<slug>/.hermes-dev/plans/<slug>.md`.

For a **change to an existing app**, skip bootstrap: reuse its folder/project (named in the task body) and its existing `.hermes-dev/`. Never scatter one app across two folders.

## Step 4 — Build the task plan

Write the plan as an ordered checklist. Each task MUST include:
- Clear deliverable and expected behavior
- File paths to change/create
- Logging requirements (what to log, where, levels) — **never create a task without logging instructions**
- Dependency notes

Right granularity: each task completable in one focused session; ordered by dependency (X before Y).

**Kanban wiring (native handoff):** for a multi-role epic, create the downstream role chain via CLI, linked in order:
```
hermes kanban --board departments create "<task>" --assignee aif_implementer --priority 5 --parent <plan_task_id> --body "<scope+files+logging+acceptance>"
hermes kanban --board departments link <impl_id> <verify_id>   # implement → verify → review
```
Assign only to real profiles (`aif_implementer`/`aif_verifier`/`aif_reviewer`). Never invent assignees.

## Step 5 — Save the plan file

Write to `.hermes-dev/plans/<slug>.md` (slug: lowercase, hyphenated, ≤50 chars). **Exact canonical
paths — do NOT improvise flat files or new folders** (E2E audit caught planners inventing
`.hermes-dev/PLAN.md`, `SPEC.md`, `test-specs/`):
- plan → `.hermes-dev/plans/<slug>.md` · spec → `.hermes-dev/specs/<slug>.md` · test matrix →
  inside the spec or `.hermes-dev/qa/<slug>/` · gate criteria → `.hermes-dev/gates/<slug>.md`
- `DESCRIPTION.md` / `ARCHITECTURE.md` / `AGENTS.md` / `README.md` → **project ROOT**, never under
  `.hermes-dev/` · roadmap → `.hermes-dev/plans/ROADMAP.md` · rules → `.hermes-dev/RULES.md` + `rules/`

Sections:
- Title + date
- `## Original Request` — the exact task/brief text, verbatim (do not translate/summarize)
- `## Settings` — Testing (yes/no), Logging (verbose default), Docs (yes/no)
- `## Tasks` — grouped by phase, each `- [ ]` with deliverable + files + logging
- `## Commit Plan` — only for 5+ tasks: checkpoints every 3–5 tasks with conventional-commit messages

## Step 6 — Hand off

Do **not** implement the plan yourself. Complete the planning task with a structured handoff (plan path, task count, downstream assignees) so `aif_implementer` picks it up. Acceptance of the whole epic = `aif_verifier` PASS + `aif_reviewer` PASS (human approval only for irreversible/prod actions).

## Important rules

1. **NO tests** if the task says no — don't sneak in test tasks.
2. **NO reports/summaries** as tasks.
3. **Actionable** — every task has a concrete deliverable + file paths.
4. **Dependencies matter** — order so work is sequential.
5. **Commit checkpoints** for 5+ tasks.
6. **Verbose, configurable logging** is planned into every implementation task.
7. **Block, don't guess** — missing input/unsafe scope → block the kanban task with the exact reason.

## References

- `references/EXAMPLES.md` — input parsing + end-to-end flow scenarios (worker vs interactive, new-app bootstrap, sequential numbering, 9999 cap, block-on-missing-input).
- `references/TASK-FORMAT.md` — plan file naming (default slug + optional sequential-prefix project rule), the full plan-file template, kanban task example with logging requirements.
- `tests/*.yaml` — spec-style fixtures documenting expected behavior (ported from lee-to; no Hermes runner consumes them yet).
