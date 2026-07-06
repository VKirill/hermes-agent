---
name: aif-rules-check
description: >-
  Standalone read-only rules compliance gate: check changed files or a git ref against
  the project rules in .hermes-dev/RULES.md and .hermes-dev/rules/, and emit a
  machine-readable gate_result (gate "rules"). Use when you need a dedicated
  project-rules check without a full review or verify pass — "check rules",
  "rules compliance", "rules gate"
  (port of lee-to AI Factory /aif-rules-check, adapted to Hermes).
tags:
  - aif
  - rules
  - quality-gate
  - dev-factory
  - kanban
---

# aif-rules-check — Rules compliance gate

Run a standalone read-only rules gate for project rules. This skill checks rule compliance only; it does not replace `/aif-review` or `/aif-verify`.

## Hermes context

- Runs as a kanban worker (or on demand in interactive sessions). Artifacts under **`.hermes-dev/`**; paths are fixed — no `.ai-factory/config.yaml`. Gate contract details live in `aif-methodology`.
- **Gate routing:** pass/warn → `kanban_complete` with the gate_result; fail → `kanban_block` with the gate_result and exact blockers. A fail MUST NOT strand the pipeline — the dev lead (`aif_planner`) spawns the fix task per the review→fix loop law.
- **Autonomous:** never wait for a human to interpret an ambiguous scope; downgrade to `WARN` per the classification rules below, or fall back to a resolvable diff.

## Step 0 — Load contract

- Read `references/RULES-CHECK-CONTRACT.md` first (in this skill folder).
- Treat it as the canonical source for verdict semantics and report structure.
- If examples in this file drift from the reference, follow the reference.

## Step 1 — Resolved paths (fixed)

Hermes uses fixed paths — no config resolution step:
- Rules axioms: `.hermes-dev/RULES.md`
- Rules directory: `.hermes-dev/rules/` (base conventions at `.hermes-dev/rules/base.md`, area rules `.hermes-dev/rules/<area>.md`)
- Plans: `.hermes-dev/plans/`
- Base branch: detect the repo default branch from git metadata (`git symbolic-ref refs/remotes/origin/HEAD` or similar); fall back to `main` only when detection is unavailable.

### Step 1.1 — Load skill context

**Read `.hermes-dev/skill-context/aif-rules-check/SKILL.md` — MANDATORY if it exists.** Project-specific rules accumulated by `/aif-evolve`. Treat them as project-level overrides for this skill; on conflict the skill-context rule wins; no conflict → apply both. They apply to all outputs, including verdict wording and report structure. **Enforcement:** before presenting the final report, verify it against all skill-context rules and fix any drift.

## Step 2 — Resolve inputs

Resolve two inputs before checking any rule:
1. **Changed scope** — the diff and file list you are evaluating
2. **Resolved rule sources** — the rule artifacts that may apply to that scope

### Step 2.1 — Resolve changed scope

**If a git ref was provided** (in the request or kanban task body):
1. Validate it first: `git rev-parse --verify <ref>`
2. If valid: `git diff --name-only <ref>...HEAD` and `git diff <ref>...HEAD`
3. If invalid: interactive session → ask what to check instead (staged/working-tree changes, or cancel); kanban worker → note the invalid ref in the report and fall back to the no-argument resolution below.

**Without a ref:**
1. Prefer staged work: `git diff --cached --name-only` / `git diff --cached`
2. Nothing staged → working tree: `git diff --name-only` / `git diff`
3. Still no local diff → branch diff: `git diff --name-only <resolved-base-branch>...HEAD` / `git diff <resolved-base-branch>...HEAD`

If there are still no changed files, return `WARN` rather than a hard failure.

### Step 2.2 — Resolve rule sources

Load rule sources in this order:
1. `.hermes-dev/RULES.md`
2. `.hermes-dev/rules/base.md`
3. Any `.hermes-dev/rules/<area>.md` files that clearly match the changed scope

Area rules are optional and scoped:
- Use changed file paths, folder names, and optional plan context to judge relevance.
- If relevance is ambiguous, mention the rule source as uncertain and keep the outcome at `WARN`, not `FAIL`.

If no rule sources resolve, return `WARN` rather than a hard failure.

### Step 2.3 — Optional plan context

Use the active plan only when it helps interpret scope or area relevance; **absence of a plan is never a failure.** Resolution order:
1. A plan explicitly named in the kanban task body / parent handoff.
2. Branch-based lookup: `branch_stem` = current branch (`git branch --show-current`) with every `/` replaced by `-` (e.g. `feature/user-auth` → `feature-user-auth`). Glob `.hermes-dev/plans/[0-9][0-9][0-9][0-9]_<branch_stem>.md` first and pick the highest-numbered match (emit `WARN [aif-rules-check] multiple sequential plans for <branch>: <list>; using <chosen>` if more than one matches); otherwise fall back to `.hermes-dev/plans/<branch_stem>.md`.
3. A single named plan in `.hermes-dev/plans/` (a leading `NNNN_` prefix counts as a match) when no branch-based plan resolves.

Do not fail the rules check because a plan file is missing or ambiguous.

## Step 3 — Evaluate rules

Read the changed files from the resolved scope and compare them against the resolved rules.

Classification rules:
- `PASS` — at least one applicable rule was checked and no clear violations were found.
- `WARN` — no applicable rules were resolved, the evidence is ambiguous, or there are no changed files to evaluate.
- `FAIL` — an explicit hard rule is clearly violated by the inspected diff or changed files. Only return `FAIL` in this case.

Evidence rules:
- Tie every blocking violation to specific rule text and at least one concrete file/path or diff hunk.
- If a rule sounds like a preference, is too vague, or cannot be verified confidently from the diff, do not escalate it past `WARN`.
- Missing optional files or a partially configured rules hierarchy are `WARN`, not `FAIL`.

## Step 4 — Read-only boundary

This skill is read-only: do not edit `RULES.md`, `rules/base.md`, area rules, plan files, or source code.

If rules are missing, stale, or need refinement:
- Suggest `/aif-rules <rule text>` for axioms
- Suggest `/aif-rules area:<name>` for area-specific rules

## Step 5 — Output + gate_result

Use the exact verdict semantics and section order from `references/RULES-CHECK-CONTRACT.md`. Required content: overall verdict, files checked, gate results, blocking violations, suggested fixes, suggested rule updates, final machine-readable `aif-gate-result` fenced JSON block.

When useful, suggest the next best workflow in the human-readable report: `/aif-review` for broader code review, `/aif-verify` for full plan-completeness verification, `/aif-rules` when the underlying rules need to be captured or corrected.

Machine-readable gate result (schema per `aif-methodology`):
- Append **one** final fenced `aif-gate-result` JSON block after the human-readable rules report, and pass it via `kanban_complete` (pass/warn) or `kanban_block` (fail).
- Use `"gate": "rules"`.
- Map the human verdict exactly: `PASS` → `pass`, `WARN` → `warn`, `FAIL` → `fail`.
- `"blocking": true` only for explicit hard-rule violations that produce a human `FAIL`.
- Include only hard-rule violations in `"blockers"`; changed/inspected paths in `"affected_files"`.
- `"suggested_next"`: `/aif-rules` when rules should be added or clarified, `/aif-fix` when code must change, or `null` when no allowed next command fits. Do NOT use `/aif-review` in the JSON `suggested_next.command` — it may appear only in human-readable workflow suggestions.

```aif-gate-result
{
  "schema_version": 1,
  "gate": "rules",
  "status": "warn",
  "blocking": false,
  "blockers": [],
  "affected_files": [],
  "suggested_next": {
    "action": "aif-rules",
    "reason": "Rules are missing or ambiguous for the changed scope."
  }
}
```

Schema reminder: `"status": "pass|warn|fail"`, `"blocking": true|false`, `"blockers": [`, `"affected_files": [`, `"suggested_next": {`.
