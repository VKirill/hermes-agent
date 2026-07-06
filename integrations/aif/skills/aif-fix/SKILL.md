---
name: aif-fix
description: >-
  Fast targeted bug-fix workflow: reproduce first (regression-first), implement the smallest
  root-cause fix with [FIX] logging, rerun the exact same check, and record a self-improvement
  patch. This is the fix half of the department's review→fix loop — fix tasks spawned by
  aif_reviewer on the departments board land here. Use when a dev task is a bugfix, or the
  user says "fix", "bug", "broken", "error", "regression", "doesn't work". Port of lee-to
  AI Factory /aif-fix, adapted to Hermes.
tags:
  - aif
  - bugfix
  - regression
  - dev-factory
  - kanban
---

# aif-fix — Bug Fix Workflow

Fix a specific bug or problem in the codebase. Supports two modes: immediate fix (default) or plan-first. The default workflow is regression-first whenever a regression check is needed: reproduce the problem, confirm the reported behavior, implement the fix, then verify the same check passes.

## Hermes context

- Runs **as a kanban worker** under `aif_implementer` on the `departments` board (also usable interactively). Native kanban is the handoff layer — **no `HANDOFF_MODE`, no MCP sync, no `.ai-factory/config.yaml`**. Fixed artifact paths: fix plan `.hermes-dev/fixes/FIX_PLAN.md`, patches `.hermes-dev/patches/`, research `.hermes-dev/research/RESEARCH.md`.
- **This skill closes the review→fix loop.** When `aif_reviewer` (or `aif_verifier`) fails a gate, it creates exactly one fix task assigned to `aif_implementer` with `--idempotency-key fix:<reviewed_task_id>` (dedupes re-runs) and links it so re-review waits on it. Your job: read the blockers from the fix task body + parent handoffs, fix them, complete on evidence — completing the fix task unblocks the linked re-review. Never leave the loop open by self-blocking on green checks.
- **Autonomous mode:** no interactive questions. Default to **Fix now**; use plan-first only when the task body says `--plan-first`. If the bug is unreproducible with no plausible root cause, or the fix would be irreversible/prod-affecting (deploy/publish/migrate/spend/force-push/merge), **block the kanban task with the exact reason**. Interactive (topic/CLI) sessions may ask clarifying questions and offer the mode choice.

## Canonical Regression-First Policy

A **regression check** is the smallest useful test, command, fixture, API call, browser scenario, script, or documented manual/runtime reproduction that proves the reported bug or validates the expected behavior.

When a bug needs regression coverage, every workflow path (fix-now, plan-first, and existing-plan execution) follows this policy:

1. Identify the minimal regression check that should reproduce the issue or encode the expected behavior.
2. Execute the check before implementation and confirm it fails or reproduces the reported problem.
3. Implement the smallest fix addressing the root cause.
4. Re-run the exact same check and confirm it passes.
5. Only after that, run related existing checks when practical and suggest broader coverage if useful.

Fallback behavior:

- If no automated/executable check is available, document the narrowest manual/runtime reproduction and why no executable check exists. Treat that documented reproduction as the regression check for step 4 when it can be rerun.
- If no useful regression check exists at all, record the reason before implementation. **Worker mode:** continue only when investigation found a plausible root cause that can be fixed safely; otherwise block the kanban task as unreproducible (include what you tried) and stop without changing implementation code. **Interactive mode:** ask whether to proceed with the likely fix, adjust reproduction, or investigate further.
- If the pre-fix regression check passes unexpectedly, treat it as a reproduction mismatch: record the command/check, inputs, environment assumptions, and observed result. Then use the same worker/interactive fallback above.

Do not duplicate or weaken this policy in later workflow steps — they reference it and add only local execution details.

## Step 0 — Load context & past experience

Read if present in the target workspace:

- The **kanban task body + parent handoffs** (`hermes kanban --board departments show <id>`) — for a fix task this carries the reviewer's blockers, affected files, and suggested rework. That is your problem statement.
- `DESCRIPTION.md` and `ARCHITECTURE.md` at the project root (fall back to `.hermes-dev/` copies) — tech stack, conventions, structure boundaries.
- `.hermes-dev/RULES.md` + `.hermes-dev/rules/*` — hard project rules.
- **`.hermes-dev/skill-context/aif-fix/SKILL.md` — MANDATORY if it exists.** Project rules accumulated by `/aif-evolve`. Treat them as project-level overrides: on conflict with this file, **skill-context wins**; they apply to ALL outputs including the FIX_PLAN.md structure and patch files. After generating any artifact, verify it against these rules and fix violations before finishing.
- **Patch fallback (only when skill-context is missing):** if `.hermes-dev/patches/` exists, Glob `*.md`, sort ascending, read the last **10** only; prioritize recurring Root Cause / Prevention patterns. If skill-context exists, do not bulk-read patches — optionally inspect a small targeted subset when tags/files clearly match the current bug.

## Step 0.1 — Check for an existing fix plan

**Before anything else**, check `.hermes-dev/fixes/FIX_PLAN.md` (or a custom plan path named in the task body).

**If it EXISTS:**

- Read it fully. If the first line carries a `<!-- hermes:task:<id> -->` annotation, that is the linked kanban task.
- If the plan contains `## Research Context` (or a `Source:` line pointing at `.hermes-dev/research/RESEARCH.md`), treat the embedded snapshot as the committed fix requirements. Open the research file only to verify the revision marker (`Updated:` / `SHA256:`). If the marker is missing or the current Active Summary differs, emit `WARN [research-drift]` and execute against the plan's embedded context — do not silently rebase onto newer research.
- Skip Step 1 (intake/mode choice), still run Step 0 context load, then continue at Step 2 using the plan as your guide. Apply the Canonical Regression-First Policy even if the plan predates it; preserve the canonical order (confirm → fix → rerun).
- After the fix is fully applied and verified (Step 4), **delete the plan only when it is the default `.hermes-dev/fixes/FIX_PLAN.md`**; custom/non-default plan paths are preserved (say so in the summary).

**If it does NOT exist and no problem description was given** (empty task body / no arguments): interactive — ask for a bug description or a plan; worker — block the task: "no fix plan and no problem description". **STOP.**

**If it does NOT exist and a description was given:** continue below.

## Step 1 — Understand the problem & choose mode

From the task body / arguments identify: the error message or unexpected behavior, where it occurs (file, function, endpoint), steps to reproduce. Interactive: if unclear, ask (expected vs actual behavior, stack trace, when it started), then offer the mode choice **Fix now / Plan first**. Worker: task body decides — `--plan-first` present → plan mode, otherwise fix now.

## Step 1.1 — Plan-first: create the fix plan (then STOP)

Investigate enough to plan (same parallel exploration as Step 2). If `.hermes-dev/research/RESEARCH.md` exists and its Active Summary is relevant, copy it into `## Research Context` with a `Source:` revision line — template, hashing and normalization rules in `references/FIX-PLAN-TEMPLATE.md`. Synthesize: root cause (or candidates), affected files/functions, impact scope. Write `.hermes-dev/fixes/FIX_PLAN.md` per the template; when working a kanban task, the **first line MUST be** `<!-- hermes:task:<task_id> -->` (omitting it when a task id is known is a bug).

Then **STOP — do NOT apply the fix**. Interactive: tell the user to review and re-run `/aif-fix` (no args) to execute. Worker: complete the planning task with a handoff (plan path, root-cause summary) so the follow-up fix task executes it.

## Step 2 — Investigate the codebase

**If subagents mode is enabled (department default), spawn 2–3 `Explore` subagents via the Agent tool in parallel; in skills mode execute the same investigations inline yourself** (Glob/Grep/Read, trace the data flow):

1. **Locate the problem area** — code related to the error location / affected functionality; read the relevant functions, trace the data flow (thoroughness: medium).
2. **Related code & side effects** — all callers/consumers of the affected function/module; what else might break (thoroughness: medium).
3. **Similar past patterns** — similar error patterns or related fixes in the codebase; `git log` for recent changes to the affected files (thoroughness: quick).

Synthesize findings into: the **root cause** (not just symptoms), related code that might be affected, existing error handling.

## Step 2.5 — Capture a regression check

Apply the **Canonical Regression-First Policy** before changing implementation code. Prefer a regression check for behavior bugs, parsing/validation bugs, API/data bugs, crashes, and regressions. If the change is a non-bug cleanup, purely static correction, or investigation-only request, record why the policy does not apply and continue.

**Anti-gaming rule:** do not tailor the test to the implementation you plan to write. The test must describe the externally expected behavior or the reported failure condition. If it passes before any fix, the reproduction is wrong, the bug is stale, or the environment differs — handle that through the policy's fallback before changing implementation code.

Record the selected check, pre-fix result, and any fallback decision so Step 4 can rerun the same check.

## Step 3 — Implement the fix

Apply the smallest root-cause fix **with logging**. Logging is MANDATORY (the user/verifier needs it to confirm the fix and to iterate if it fails):

1. **Prefix** `[FIX]` (or `[FIX:<issue-id>]`) for easy filtering.
2. **Log inputs** being processed, **log success**, **log errors** with full context (message + stack).
3. **Configurable** — gate on `LOG_LEVEL` / a debug env flag; never hard-code always-on noise, never skip logging "to keep code clean".

```typescript
const LOG_FIX = process.env.LOG_LEVEL === "debug" || process.env.DEBUG_FIX;
if (LOG_FIX) console.log("[FIX] Input:", input);
// ... fix logic ...
if (LOG_FIX) console.log("[FIX] Output:", result);
```

## Step 4 — Verify the fix

- Code compiles/runs.
- If Step 2.5 created, identified, or documented a regression check — rerun/revisit the **same** check and confirm the fixed behavior.
- Verify the logic is correct; ensure no regressions introduced.
- When practical, run the closest related existing test suite after the regression check passes.

## Step 5 — Suggest additional test coverage

Always surface broader coverage that would prevent nearby regressions (edge cases around the bug, empty states, boundary inputs). **Interactive:** show the "Fix Applied" summary (template in `references/EXAMPLES.md`) and ask whether to create the additional tests now; on "yes", write them following project test conventions and run them. **Worker:** include the suggestions in the completion handoff; create the extra tests only when the task/plan settings say tests are in scope.

## Step 6 — Create a self-improvement patch (ALWAYS)

Every fix generates a patch — it is a learning artifact, not a report. `mkdir -p .hermes-dev/patches`, then write `.hermes-dev/patches/YYYY-MM-DD-HH.mm.md` using the template in `references/PATCH-TEMPLATE.md` (Problem / Root Cause / Solution / Prevention / Tags — Root Cause is the most valuable part: WHY, not just what). **This is NOT optional.**

## Completion — hand off on evidence

Worker: return a structured handoff — issue, root cause, fix, regression check command + pre/post results (or "not available: <reason>"), files modified, logging added, patch path, remaining non-blocking warnings — then `kanban_complete`. For a `fix:<reviewed_task_id>` task this unblocks the linked re-review; do not self-block waiting for approval when checks are green. Interactive: show the same summary and suggest `/clear` or `/compact` if context is heavy.

## Important rules

1. **Check the fix plan first** — always check `.hermes-dev/fixes/FIX_PLAN.md` before anything else.
2. **Plan mode = plan only** — create the plan and STOP; do not fix.
3. **Execute mode = follow the plan** step by step; delete only the default plan path after verified execution.
4. **NO reports** — no summary documents (patches are learning artifacts, not reports).
5. **ALWAYS log** — every fix ships `[FIX]` logging for feedback.
6. **Regression-first when checks are needed** — follow the Canonical Regression-First Policy; confirm the problem when reproducible; verify the same check after the fix.
7. **Do not fit tests to implementation** — regression tests encode reported/expected behavior, not internal shape.
8. **ALWAYS suggest additional tests** beyond the required regression check.
9. **Root cause** — fix the actual problem, not symptoms.
10. **Minimal changes** — don't refactor unrelated code; **no features while fixing**; one fix at a time.
11. **Ownership boundary** — this skill owns `.hermes-dev/fixes/` and `.hermes-dev/patches/`; DESCRIPTION.md, ARCHITECTURE.md, roadmap and rules artifacts are read-only here.
12. **Logging scope** — `[FIX]` prefix is for fix code; context-gate output uses `WARN`/`ERROR` and never changes global logging policy in other skills.
13. **Escalate scope honestly** — if investigation reveals the "bug" is really a design change needing decomposition, hand it to `aif-plan` (comment + block/route the task) instead of silently expanding the fix.
14. **Block only for real reasons** — unreproducible with no plausible root cause, missing context/access, or an irreversible/prod action.

## DO NOT

- ❌ Apply a fix in plan-first mode — create the plan and stop.
- ❌ Skip the fix-plan check at the start.
- ❌ Leave the default `.hermes-dev/fixes/FIX_PLAN.md` behind after successful execution (or delete custom plan paths).
- ❌ Generate reports or summaries (patches are not reports).
- ❌ Refactor unrelated code, add features, skip logging, skip the test suggestion, or skip patch creation.
- ❌ Self-block a `fix:` task when checks are green — that dams the review→fix loop.
