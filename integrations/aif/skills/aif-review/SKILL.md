---
name: aif-review
description: >-
  Independent code review of implemented changes (or a PR/diff) for correctness, security,
  performance, and maintainability. Distinguishes blocking issues from suggestions and emits
  a machine-readable gate_result. Use when a completed implementation needs review before
  acceptance, or the user says "review code", "check my code", "review PR". This is the
  aif_reviewer role skill (port of lee-to AI Factory /aif-review, adapted to Hermes).
tags:
  - aif
  - code-review
  - quality-gate
  - dev-factory
  - kanban
---

# aif-review — Independent review gate

Review changes for correctness, maintainability, contract alignment, security/rules risk, and production readiness. Do not rewrite the implementation during review unless explicitly scoped.

## Hermes context
Runs as a kanban worker under `aif_reviewer`. Artifacts under `.hermes-dev/`. No `HANDOFF_MODE`/MCP/config.yaml. Read-only for context artifacts. **On a fail verdict you MUST close the loop** (see below) — never leave a blocker without an assigned fixer.

## Step 0 — Scope & context
Determine what to review: the kanban task's changed files (default), or a diff/PR if given (`git diff --cached`, `gh pr diff <n>`, or `git log <ref>..HEAD`). Read the project-root `ARCHITECTURE.md`, `.hermes-dev/RULES.md`, acceptance criteria, and `.hermes-dev/skill-context/aif-review/SKILL.md` (**MANDATORY if it exists**). Verify claims against files/commands where feasible.

## Review checklist
- **Correctness:** logic errors, edge cases, null/undefined, error handling, type safety.
- **Security:** injection (SQL/command/XSS), secrets exposure, auth/authz, input validation, CSRF. (Deep pass → aif-security-checklist.)
- **Performance:** N+1 queries, memory leaks, inefficient algorithms, missing indexes, large payloads.
- **Best practices:** duplication, dead code, magic values, naming, SOLID/DRY.
- **Testing:** coverage for new code, edge cases tested.
- **Context gates (read-only):** Architecture boundary/dependency alignment; explicit RULES.md violations.

## Output — findings + gate_result
Human summary: **Critical Issues** (behavioral impact → optional citation → `file:line` → concrete fix) and **Suggestions** (non-blocking, same shape), plus Questions / Positive Notes. Then append the final machine-readable block and pass it to `kanban_complete` (pass/warn) or `kanban_block` (fail):

```aif-gate-result
{
  "schema_version": 1,
  "gate": "review",
  "status": "pass",
  "blocking": false,
  "blockers": [],
  "affected_files": [],
  "suggested_next": { "action": "aif-commit", "reason": "Review found no blocking issues." }
}
```
- `status`: `fail` when any Critical Issue or blocking context-gate finding remains; `warn` for suggestions/uncertainty only; `pass` when clean. A failing context gate keeps `fail` even with zero critical issues.
- `blocking`: true only when `fail`. `blockers`: merge-blocking findings only. `affected_files`: reviewed/implicated paths.

## On a FAIL verdict — close the review→fix loop (department hard rule)

**Workflow card** (your task context shows an "AIF workflow stage" banner): call
`kanban_block(reason=..., gate_result=<fail verdict>)` and STOP — the convergence gate routes the
card back to `implementing` with your blockers carried, or to a human when the iteration cap trips.
Do NOT create a fix task yourself. Blocker summaries must stay stable across rounds (same wording →
same finding id) so convergence can be proven; word genuinely new problems differently.

**Multi-card pipeline** (no workflow banner): besides `kanban_block`, create exactly one fix task
for the implementer and link it so re-review waits:
```
hermes kanban --board departments create "<what to fix>" --assignee aif_implementer --priority 5 \
  --parent <implementation_task_id> --idempotency-key fix:<reviewed_task_id> \
  --body "<concrete blockers + suggested rework + where to look>"
hermes kanban --board departments link <fix_id> <this_review_task_id>
```
`--idempotency-key` prevents duplicates on re-runs. Put `fix_task_id` in the gate_result. Do not PASS until the fix lands and re-review passes.

## Style
Constructive, prioritized, explain the "why", cite `file:line`, acknowledge good code. Read-only for context — suggest owner commands (`/aif-rules`, `/aif-architecture`) instead of editing artifacts.

## References

- `references/SEVERITY.md` — single source of truth for critical vs suggestion severity and when an item may be reclassified.
- `references/CHECK-MODE.md` — the opt-in `+check` findings-validation pass (procedure, failure modes, gate_result recomputation).
- `references/VALIDATOR.md` — the fresh-context validator subagent prompt template dispatched by `+check` via the Agent tool.
- `tests/*.spec.yaml` — spec-only fixtures documenting the `+check` contract (ported from lee-to; no Hermes runner consumes them yet).
