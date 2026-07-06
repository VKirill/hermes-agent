---
name: aif-improve
description: >-
  Refine an existing implementation plan with a second iteration — the optional plan-polish
  stage between aif-plan and aif-implement. Re-analyzes the codebase for gaps, missing tasks,
  vague descriptions, and wrong dependencies; optional +check flag validates findings via a
  fresh-context subagent. Use after planning ("improve the plan", "refine plan", "review the
  plan", "second pass") or to polish an aif-fix plan. Port of lee-to AI Factory /aif-improve,
  adapted to Hermes.
tags:
  - aif
  - planning
  - plan-refinement
  - dev-factory
  - kanban
---

# aif-improve — Plan Refinement (Second Iteration)

Refine an existing plan by re-analyzing it against the codebase. Finds gaps, missing tasks, wrong dependencies, and enhances task quality.

## Core Idea

```
existing plan + deeper codebase analysis + user feedback (optional)
    ↓
find gaps, missing edge cases, wrong assumptions
    ↓
enhanced plan with better tasks, correct dependencies, more detail
```

## Hermes context

- The **optional polish stage between `aif-plan` and `aif-implement`**. Runs interactively or as a kanban worker on the `departments` board. **No `HANDOFF_MODE`, no `.ai-factory/config.yaml`** — fixed paths: plans `.hermes-dev/plans/`, fix plan `.hermes-dev/fixes/FIX_PLAN.md`, research `.hermes-dev/research/RESEARCH.md`, patches `.hermes-dev/patches/`, archive `.hermes-dev/archive/`.
- **Autonomous mode:** no interactive questions. Apply improvements that are traceable to codebase evidence (or the task's improvement prompt) directly, and put the full refinement report into the completion handoff. If no plan resolves, **block the kanban task** naming the missing input. Interactive sessions ask for approval before applying (see Step 5).
- The plan file's checkboxes are the source of truth for progress. If the epic is wired into kanban subtasks, keep them in sync (Step 6).

## Step 0 — Parse arguments & load skill context

Parse the invocation arguments:

```
- --list    → list available plans only (read-only, then STOP)
- +check    → after refinement, validate findings via a fresh-context subagent
- @<path>   → explicit plan file override (highest priority)
- remaining argument text → optional improvement prompt
```

`+check` is orthogonal and may appear anywhere; strip it before resolving `@<path>` and the prompt. When `--list` is present it wins and no refinement is executed — `+check` is silently ignored in `--list` mode (nothing to validate).

**Read `.hermes-dev/skill-context/aif-improve/SKILL.md` — MANDATORY if it exists.** Project rules accumulated by `/aif-evolve`; treat as project-level overrides (on conflict, skill-context wins). They apply to ALL outputs — the refinement report and any plan modifications ("tasks MUST include X" → apply while refining). Verify every output against these rules before presenting; violations are bugs to fix first.

### Step 0.list — List available plans (`--list`)

If arguments contain `--list`, execute the procedure in `references/LIST-MODE.md` and STOP. That document is the single source of truth for discovery rules, output shape, and the read-only contract. Do not duplicate it here.

## Step 1 — Resolve the active plan

Pick **one** plan file for refinement using this priority:

```
1. @<path> override — resolve relative to project root (absolute allowed);
   missing file → "Plan file not found: <path>" and STOP (worker: block).
2. Branch-based: git branch --show-current → <branch-slug> (replace "/" with "-").
   → Glob .hermes-dev/plans/[0-9][0-9][0-9][0-9]_<branch-slug>.md (numbered plans):
     0 matches → fall through; 1 match → use it; >1 → use the highest-numbered and emit
     WARN [aif-improve] multiple sequential plans for <branch>: <list>; using <chosen>
   → Otherwise .hermes-dev/plans/<branch-slug>.md
3. No branch match (or not a git repo) → if .hermes-dev/plans/ contains exactly one *.md
   plan (a leading 4-digit prefix counts), use it. Multiple → interactive: ask the user to
   choose / require @<path>; worker: use the plan named in the kanban task body, else block.
4. Fix plan at .hermes-dev/fixes/FIX_PLAN.md (from aif-fix plan mode).
```

Discovery scans `.hermes-dev/plans/` only — plans archived to `.hermes-dev/archive/plans/` by `/aif-archive` are excluded. **If no plan is found anywhere:** interactive — suggest `/aif-plan <description>` or `/aif-fix <bug description>` and STOP; worker — block with "no active plan found".

## Step 2 — Load context

**2.1 Read the plan file completely.** Understand: feature scope and goals; `## Original Request` when present (the original user intent and immutable scope anchor — raw source input, preserve it exactly on any edit or regeneration); current tasks (subjects, descriptions, dependencies); settings (testing, logging preferences); commit checkpoints; which tasks are already completed (`- [x]`).

**2.2 Read project context.** `DESCRIPTION.md` at the project root: tech stack, architecture, conventions, non-functional requirements.

**Research drift:** if the plan contains `## Research Context` (or a `Source:` line pointing at the research file), treat the embedded snapshot as the committed requirements. Open `.hermes-dev/research/RESEARCH.md` only to verify the revision marker (`Updated:` / `SHA256:`) and consult `## Sessions` for rationale. If the marker is missing or the current Active Summary revision differs, emit `WARN [research-drift]` and refine against the plan's embedded Research Context — do not apply requirements from newer research unless explicitly asked to rebase. Otherwise, read the research file if it exists and is relevant. When adding `## Research Context` to an unlinked plan, hash the normalized copied Active Summary (exclude the `Source:` line and comments; preserve line order; trim trailing spaces; LF endings; exactly one final newline) by feeding it via stdin to `shasum -a 256` (or `sha256sum`) — never through a temp file; the first output field is the `SHA256:` value.

**2.3 Patches (limited fallback).** Only when skill-context is missing and `.hermes-dev/patches/` exists: Glob `*.md`, sort ascending, read the last **10**; focus on reusable Prevention / Root Cause patterns that affect planning quality. If skill-context exists, do not bulk-read patches; optionally inspect a small targeted subset for a known recurring issue.

**2.4 Load current task state.** The plan's checkboxes are authoritative. If the epic has kanban subtasks, `hermes kanban --board departments show <id>` the relevant ones to learn what is created / in progress / completed.

## Step 3 — Deep codebase analysis

Go **deeper** than the original `aif-plan` pass:

- **3.1 Trace existing code paths.** For each task, Glob/Grep/Read the files it mentions. Look for: existing patterns the plan should follow; code that already partially implements a task; hidden dependencies the plan missed; shared utilities/services to reuse instead of creating new ones.
- **3.2 Check integration points** the plan might have missed: API routes needing updates, database migrations, config changes, import/export updates, middleware/guards that apply, existing validation patterns.
- **3.3 Check edge cases** for this stack: error handling patterns used in the project, null/undefined safety, authn/authz checks, rate limiting and caching, data validation at boundaries.

## Step 4 — Identify improvements

Compare the plan against findings. Use `## Original Request` as the scope anchor (with the current task list and any committed `## Research Context`). A refinement is in scope only when it supports the original request or an explicitly given improvement prompt; otherwise route it to 4.6 (`out_of_scope`). Categorize:

- **4.1 Missing tasks** — should exist but don't (migration, config update, index creation); uncovered edge cases.
- **4.2 Task quality issues** — vague descriptions (no file paths, no implementation detail), missing logging requirements, missing error-handling detail, incorrect file paths.
- **4.3 Dependency issues** — wrong order (A depends on B but B comes later), missing dependencies, unnecessary dependencies (parallelizable work).
- **4.4 Redundant/duplicate tasks** — two tasks doing the same thing; a task unnecessary because the code already exists; duplicated functionality.
- **4.5 Task size issues** — too large (split) or too small (merge); report these under "📝 Task Improvements" (`improvements` group, alongside 4.2) — they restructure existing tasks.
- **4.6 Out-of-scope tasks** — useful in themselves but unrelated to this plan's feature (gold-plating). On approval they are dropped like `removals`; the difference is the report only — they get their own "💡 Out of scope" section so the useful-but-unrelated idea is visible before being dropped. The skill does not persist out-of-scope items anywhere.
- **4.7 User-prompted improvements** — a dispatcher, not a group: each finding produced by the improvement prompt routes to its natural group (new task → 4.1, reword/expand → 4.2, explicit removal → 4.4, useful-but-elsewhere → 4.6). There is no separate 4.7 group in the report or in `+check` validation.

### Optional: `+check` validation between Step 4 and Step 5

When `+check` is set (and `--list` is not), run the procedure from `references/CHECK-MODE.md` here. It re-reads cited files via a fresh-context subagent (Agent tool, `general-purpose`), drops invented items, rewrites partially-correct ones, and recomputes dependencies on the filtered list. Without `+check`, skip entirely — no validator lines appear and the Summary block stays in its default shape.

## Step 5 — Present improvements

Emoji-grouped sections for scannability; items in "🆕 Missing Tasks", "📝 Task Improvements", "🗑️ Removals", and "💡 Out of scope" share one prose shape (no labeled `Why:`/`Issue:`/`Fix:` fields): **behavioral impact** (what breaks or gets harder as-is) → **optional note** (codebase citation / existing pattern / consequence, only when it adds signal) → **plan anchor** (`Task #X`, or "after Task #X" for new tasks) → **suggested edit** (what to add / how to reword / what to remove). "🔗 Dependency Fixes" is always computed after the other four groups (and after `+check` filtering) and keeps the short legacy form: `Task #X should depend on Task #Y. Reason: …`, referencing only surviving tasks.

```
## Plan Refinement Report

Plan: [plan file path]
Tasks analyzed: N

### Findings

#### 🆕 Missing Tasks (N found)
#### 📝 Task Improvements (N found)
#### 🔗 Dependency Fixes (N found)
#### 🗑️ Removals (N found)
#### 💡 Out of scope — for later (N found)

#### 📋 Summary
- Missing tasks: N
- Tasks to improve: N
- Dependencies to fix: N
- Tasks to remove: N
- Out of scope: N
```

When `+check` ran successfully, append `- Hidden by +check: N` and `- Adjusted by +check: M` to the Summary (exact wording and failure-mode replacements in `references/CHECK-MODE.md`). Worked prose examples of each section live in `references/EXAMPLES.md`.

**Approval:** interactive — ask "Apply these improvements?" (Yes, apply all / Let me pick / No, keep as is) and act accordingly. Worker — apply all evidence-backed findings and include the full report in the completion handoff. **If no improvements found:** report "plan looks solid" (plan path + task count), suggest `aif-implement`, and finish (worker: `kanban_complete` with that evidence).

## Step 6 — Apply approved improvements

- **6.1 Improve existing tasks** — rewrite subjects/descriptions in the plan file.
- **6.2 Add missing tasks** — insert `- [ ]` entries in the correct phase, with deliverable + file paths + logging requirements (never add a task without logging instructions).
- **6.3 Fix dependencies** — reorder tasks / note dependencies so work is sequential.
- **6.4 Remove redundant or out-of-scope tasks** — both `removals` and `out_of_scope` drop the task from the plan; the distinction lives in the report only. Capturing an out-of-scope idea elsewhere (tracker, backlog) is the user's call.
- **6.5 Update the plan file (CRITICAL)** — the file must match the final state: new tasks in the correct phase; updated descriptions; fixed ordering; deleted tasks removed; commit checkpoints adjusted if task count changed significantly; **preserve every `- [x]` completed task exactly**; **preserve `## Original Request` verbatim** (heading, body, whitespace — never translate/summarize/normalize); **preserve `## Research Context` + its `Source:` revision marker exactly** unless explicitly asked to rebase (drift → keep committed context and put `WARN [research-drift]` in the report); if refining an unlinked plan with current research, add `## Research Context` with the stdin-hashed `SHA256:` marker (Step 2.2 rules). Use `Edit` for surgical changes or `Write` to regenerate when changes are extensive. **Filename invariant:** a sequential name (`^[0-9]{4}_.*\.md$`, e.g. `0042_feature-user-auth.md`) keeps its exact numeric prefix on rewrite — never renumber during an improve pass; write back to the same path you read from.
- **Kanban sync:** if the epic has kanban subtasks, mirror the changes — create tasks for added work per the `aif-plan` Step 4 convention (`hermes kanban --board departments create … --assignee aif_implementer`), comment on tasks whose scope changed, and link new dependencies.
- **6.6 Confirm completion** — report: added N tasks / improved N descriptions / fixed N dependencies / removed N tasks; updated plan path; total tasks; next step `aif-implement`. Interactive: suggest `/clear` or `/compact` if context is heavy.

## Artifact ownership

- Primary ownership: the plan artifact being refined (branch plan, named plan, or the fix plan when explicitly targeted).
- Read-only context: description, architecture, roadmap, rules, and research artifacts — everything except the active plan file itself.

## Important rules

1. **Don't rewrite from scratch** — improve the existing plan, don't replace it.
2. **Preserve completed work** — never modify or remove `- [x]` tasks.
3. **Traceable improvements** — every change justified by codebase analysis or the improvement prompt.
4. **Respect settings** — testing "no" → no test tasks; logging "minimal" → no verbose-logging tasks.
5. **No gold-plating** — don't propose tasks outside the feature scope unless critical; an existing task that drifted out of scope goes to "💡 Out of scope", not "🗑️ Removals".
6. **Minimal viable improvements** — suggest only what matters, not every possible enhancement.
7. **Approval before applying** — interactive sessions never apply without user confirmation; workers apply on evidence and report in the handoff.
8. **Keep plan file in sync** — the plan file MUST match the applied state (and kanban subtasks, when wired).
9. **Original Request is immutable** — use it to judge scope; preserve it verbatim on every edit or regeneration.

## Examples

Worked examples for the default, prompt-driven, no-plan, explicit-plan-file, and "plan looks solid" flows: `references/EXAMPLES.md`. The `--list` mode example: `references/LIST-MODE.md`; the `+check` example: `references/CHECK-MODE.md`.
