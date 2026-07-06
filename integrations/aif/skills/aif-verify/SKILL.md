---
name: aif-verify
description: >-
  Verify that completed implementation matches the plan — all tasks fully done, nothing
  forgotten, code compiles, tests/lint pass, no leftover markers or undocumented config.
  Emits a machine-readable gate_result. Use after aif-implement, or when the user says
  "verify", "check work", "did we miss anything". This is the aif_verifier role skill
  (port of lee-to AI Factory /aif-verify, adapted to Hermes).
tags:
  - aif
  - verification
  - quality-gate
  - dev-factory
  - kanban
---

# aif-verify — Post-implementation quality gate

Verify the implementation against the plan with **real commands**, then emit a gate_result. You are the acceptance authority: a PASS here (plus aif_reviewer) IS the acceptance — human approval is only for irreversible/prod actions.

## Hermes context
Runs as a kanban worker under `aif_verifier`. Artifacts under `.hermes-dev/`. No `HANDOFF_MODE`/MCP/config.yaml. Autonomous: block only when checks fail or cannot be run; never turn "no human approval" into a blocker.

## Step 0 — Load context
Read the kanban task + parent handoffs, the plan at `.hermes-dev/plans/<slug>.md`, `DESCRIPTION.md` and `ARCHITECTURE.md` at the project root, `.hermes-dev/RULES.md`, and `.hermes-dev/skill-context/aif-verify/SKILL.md` (**MANDATORY if it exists**). Gather changed files (`git diff --name-only <base>...HEAD`, or the working tree if no git). `--strict` flag → strict mode (below).

## Step 1 — Task completion audit
Go through **every** task in the plan and confirm it was actually implemented (use Glob/Grep/Read to find the real code, not just "something was written"):
- `✅ COMPLETE` — all requirements verified in code
- `⚠️ PARTIAL` — some requirements missing (list them)
- `❌ NOT FOUND` — implementation not detected
- `⏭️ SKIPPED` — intentionally skipped

## Step 2 — Code quality checks (detect + run)
- **Build/compile:** `go build ./...` / `npx tsc --noEmit` / `npm run build` / `python -m py_compile` / `cargo check` / `composer validate` per stack.
- **Tests:** `pytest` / `npm test` / `go test ./...` / `phpunit` / `cargo test` — if tests existed or were planned. Report failures with file:line.
- **Lint (changed files only):** eslint / golangci-lint / ruff / php-cs-fixer.
- **Deps/imports:** no unused imports; new deps actually added; no imports of missing packages.

## Step 3 — Consistency
- Plan↔code drift (naming, file locations, API contracts).
- Leftover markers in changed files: grep for TODO/FIXME/HACK/XXX/TEMP/PLACEHOLDER/debug prints.
- New env vars / config referenced but undocumented (cross-check `.env.example`/README).
- **Context gates (read-only):** Architecture gate + Rules gate → pass/warn/fail. A failing context gate fails verification even with zero task issues.

## Step 4 — Report + gate_result
Emit a human-readable Verification Report (task table, build/test/lint status, issues found), then append **exactly one** machine-readable block as the final output, and pass it to `kanban_complete` (pass/warn) or `kanban_block` (fail):

```aif-gate-result
{
  "schema_version": 1,
  "gate": "verify",
  "status": "pass",
  "blocking": false,
  "blockers": [],
  "affected_files": [],
  "suggested_next": { "action": "/aif-review", "reason": "Verification passed without blockers." }
}
```
- `status`: `fail` = incomplete required tasks / failed blocking checks / strict-mode gate failure; `warn` = only non-blocking warnings / accepted gaps; `pass` = clean.
- `blocking`: true only when `fail`. `blockers`: blocking findings only. `affected_files`: files evaluated. `suggested_next.action` ∈ {aif-fix, aif-review, aif-rules, null}.
- **Workflow card** (task context shows an "AIF workflow stage" banner): a FAIL goes to `kanban_block(reason=..., gate_result=<fail verdict>)` — the convergence gate returns the card to `implementing` with your blockers carried, or hands off to a human at the iteration cap. Keep blocker summaries stable across rounds. Do not create fix tasks yourself.

## Strict mode (`--strict`)
All tasks COMPLETE; build/tests/lint must pass (zero warnings); no leftover markers; no undocumented env vars; architecture + rules gates must pass. Recommended before merge.

## Rules
Read-only for `.hermes-dev/*` context artifacts (report drift, suggest owner command — don't edit). No reports/summaries as artifacts. Deterministic checks over opinion.

## References

- `references/GATE-RESULT-CONTRACT.md` — the full machine-readable `aif-gate-result` schema (fields, status semantics, suggested_next allowlist) behind the aif-methodology summary.
- `references/CONTEXT-GATES-AND-OWNERSHIP.md` — which skill owns which `.hermes-dev/` artifact, and pass/warn/fail thresholds for the architecture/rules/roadmap context gates in normal vs strict mode.
- `tests/*.yaml` — spec-style fixtures documenting expected behavior (ported from lee-to; no Hermes runner consumes them yet).
