---
name: aif-evolve
description: >-
  Self-improve AIF skills from accumulated patches, project context, and codebase
  patterns. Analyzes what went wrong and what works, then writes project-specific rules
  into .hermes-dev/skill-context/ so future runs avoid past mistakes. Use after completed
  tasks / a batch of fixes, or when the user says "evolve", "extract lessons", "make the
  AI smarter for this project". Port of lee-to AI Factory /aif-evolve, adapted to Hermes.
tags:
  - aif
  - evolution
  - self-improvement
  - skill-context
  - dev-factory
---

# aif-evolve — Skill Self-Improvement

Analyze project context, patches, and codebase to improve existing skills. Makes the department smarter with every run.

## Core idea

```
patches (past mistakes) + project context + codebase patterns
    ↓
analyze recurring problems, tech-specific pitfalls, project conventions
    ↓
enhance skills with project-specific rules, guards, and patterns
```

## Hermes context

- Runs as a kanban worker (post-task lesson extraction) or interactively. Native kanban is the handoff layer — **no `HANDOFF_MODE`, no `.ai-factory/config.yaml`**. Paths are fixed:
  - Raw patches: `.hermes-dev/patches/*.md` (written by `aif-fix`)
  - Evolution logs + cursor: `.hermes-dev/evolution/`
  - Project rules output: `.hermes-dev/skill-context/<skill-name>/SKILL.md`
  - Base skills: `~/.hermes/skills/<skill-name>/SKILL.md` (verify existence via `hermes skills list`)
- **Autonomous:** kanban workers do not ask questions. Apply the documented non-interactive defaults (Steps 4 and 7) and record every decision in the evolution log. Interactive (topic/CLI) sessions may ask, in batches as described.

## Patch consumption policy

Two-layer learning model:

1. **Raw patches** (`.hermes-dev/patches/*.md`) are the source material.
2. **Skill-context rules** (`.hermes-dev/skill-context/*`) are the compact, reusable output.

Policy across workflow skills:
- `aif-evolve` is the primary raw-patch analyzer. It processes patches **incrementally** using a cursor.
- `aif-implement`, `aif-fix`, and `aif-improve` should prefer skill-context first; raw patches are fallback context only.
- Force full re-analysis only when needed (reset the cursor and rerun evolve).

## Critical: never edit installed `aif-*` skills directly

**NEVER modify any files inside `~/.hermes/skills/aif-*/`.** They are department-wide, shared across all projects, and refreshed by the port process — direct project-specific edits will be lost and would leak one project's rules into every other project. Never touch profile SOULs either.

**ALWAYS write project-specific rules to skill-context in the target workspace:**
```
.hermes-dev/skill-context/<skill-name>/SKILL.md
```
This is the ONLY correct target for `aif-*` skill improvements. No exceptions.

## Workflow

### Step 0.1 — Resolve target

Normalize the skill name from the invocation argument or the kanban task body:

| Input              | Resolved skill name |
|--------------------|---------------------|
| `plan`             | `aif-plan`          |
| `aif-plan`         | `aif-plan`          |
| `/aif-plan`        | `aif-plan`          |
| `my-custom-skill`  | `my-custom-skill`   |

Rule: strip any leading `/`. Then: if the argument does not start with `aif-` AND a skill named `aif-<argument>` exists — use `aif-<argument>`. Otherwise use as-is.

**Verify the resolved skill exists** (`~/.hermes/skills/<resolved-name>/SKILL.md`, or `hermes skills list`). If not found — report the error and stop (worker: `kanban_block` with "Skill '<resolved-name>' not found; run evolve without a target to evolve all skills, or specify a valid name").

Scope: a specific skill name → evolve only that skill; `all` or no argument → evolve all installed skills.

### Step 0.2 — Load context

Read if present in the target workspace:
- `DESCRIPTION.md` (project root) — tech stack, architecture, conventions
- `ARCHITECTURE.md` (project root) and `.hermes-dev/RULES.md` (+ `.hermes-dev/rules/*`) — this context informs convention analysis and gap detection but does not change artifact ownership

**Read skill-context files for target skills:**
- Specific skill (e.g. target `aif-plan`) → read only:
  1. `.hermes-dev/skill-context/aif-plan/SKILL.md` (target's context)
  2. `.hermes-dev/skill-context/aif-evolve/SKILL.md` (evolve's own context, if it exists **and** the target is not `aif-evolve` itself)
- All skills → read all: `.hermes-dev/skill-context/*/SKILL.md` (this already includes evolve's own context — do NOT read it separately)

Keep them in memory — they affect gap analysis in Step 5. Skill-context rules are **project-level overrides**: on conflict with the base SKILL.md of the target skill, skill-context wins (same principle as nested CLAUDE.md files).

**Applying evolve's own skill-context rules:** when a skill-context rule conflicts with a general rule in this file, the skill-context rule wins; when there is no conflict, apply both. Do NOT ignore skill-context rules even if they contradict this skill's defaults — they exist because the project's experience proved the default insufficient. **CRITICAL:** they apply to ALL outputs of this skill — the evolution report, proposed improvements, skill-context edits, and stale rule analysis. **Enforcement:** after generating any output artifact, verify it against all skill-context rules; fix violations before presenting/saving.

### Step 1 — Collect intelligence

**1.1 Read patches incrementally (cursor-based)**

Glob `.hermes-dev/patches/*.md`. Cursor file: `.hermes-dev/evolution/patch-cursor.json`:

```json
{ "last_processed_patch": "YYYY-MM-DD-HH.mm.md", "updated_at": "YYYY-MM-DD HH:mm" }
```

Processing rules:
1. Sort patch files by filename ascending (timestamp format is lexical-friendly).
2. No cursor file → first run: read all patches.
3. Cursor exists and its referenced patch is present → read only patches with filename `>` `last_processed_patch`.
4. Cursor exists but referenced patch is missing (deleted/renamed) → emit `WARN [evolve]` and do a full rescan.
5. Historical edits/deletes older than the cursor are not reliably detectable without a saved baseline — do NOT warn about them by default; warn only when a reliable baseline exists and drift is actually detected.
6. Full rescan procedure: delete `.hermes-dev/evolution/patch-cursor.json`, rerun evolve.
7. **Do not advance the cursor in this step.** Cursor updates only after a successful apply/log write in Step 7.3.

**Overlap window (anti-miss guard):** in incremental mode, ALSO read the newest 5 patches by filename (tail-5), de-duplicated. Track separately: "New patches" (filename `>` cursor), "Overlap patches" (tail-5), "Processed" = union. Cursor updates in Step 7.3 MUST be based on New patches only — never advance the cursor when only overlap patches were processed.

For each patch extract: **problem categories** (null-check, async, validation, types, API, DB, …), **root cause patterns**, **prevention points** — each independent actionable rule from the Prevention/Solution section — and **tags**. A single patch often contains **multiple independent prevention points targeting different skills**: extract EACH separately with its target skill(s), never treat a patch as one unit.

**Build a Prevention Point Registry** — a flat list of ALL extracted prevention points across this run's processed patch set (primary input for Step 5):

```
| # | Patch | Prevention Point (specific action) | Target Skill(s) |
```

**CRITICAL:** a patch with 5 prevention points produces 5 rows, not 1. A prevention point targeting 2 skills appears once with both skills listed — and EACH skill is checked independently in Step 5. In incremental mode the registry reflects this run's patch set; use a full rescan for historical backfill.

**1.2 Aggregate patterns**

Group by tags/categories. Identify: **recurring problems** (same tag 3+ times = systemic), **tech-specific pitfalls** (React re-renders, Laravel N+1, …), **missing guards** (checks that would have prevented the bugs).

**1.3 Read codebase conventions**

Scan for: linter configs (`.eslintrc`, `phpstan.neon`, `ruff.toml`, …), test patterns (file structure, assertions), error handling style, logging patterns (logger, format, levels), import conventions and file structure. When evolving a specific skill, focus the scan on areas relevant to it (for `aif-plan` — file structure and naming; for `aif-fix` — error handling and testing).

### Step 2 — Read target skills

Read ONLY the base SKILL.md files for target skills — not all skills:
- Specific skill → `~/.hermes/skills/<name>/SKILL.md`
- All skills → `~/.hermes/skills/*/SKILL.md`

Keep the loaded content in memory — Step 3 compares against it (do NOT re-read).

### Step 3 — Check for stale rules in skill-context

Run for every **target** `aif-*` skill that has a skill-context file.

**Scope constraint:** Step 3 can ONLY modify or remove skill-context files. It must NEVER propose editing, deleting, or reverting base `~/.hermes/skills/aif-*/` files — even if the base contains errors, that is outside evolve's scope.

Compare each skill-context rule against the base SKILL.md content (from Step 2):

- **Case A — base fully covers the rule (equivalent or superset):** base now has the same rule or more (e.g. skill-context has Wave 1+3, base has Wave 1+2+3). Do NOT auto-remove. Collect for Step 4 as "Fully covered by base — recommend removing from skill-context". Note: keeping it is valid — skill-context has priority, so keeping acts as a guarantee the complete version is always applied.
- **Case B — base contradicts the rule:** collect for Step 4 as "Conflict — decision required". Do NOT auto-remove.
- **Case C — partial overlap (either direction):** neither fully covers the other (e.g. skill-context has A→B→C, base has A→C→D). Do NOT auto-narrow. Analyze whether parts depend on each other (ordering, prerequisites, data flow); collect for Step 4 with the analysis. **Priority warning:** skill-context wins on the same topic — if it is kept as-is, the base's unique parts will likely be LOST. Always state this consequence.
- **Case D — no overlap:** still unique to the project. Keep as-is, no action.

### Step 4 — Present & resolve stale rules

**Skip** if no Case A/B/C findings. Present findings using the stale rules report format in `references/FORMATS.md` (base vs skill-context comparison per rule). All decisions here affect ONLY skill-context files.

**Interactive sessions:** collect decisions in batches of up to 3 per question round; do not proceed to Step 5 until all are resolved and applied.

**Kanban workers (non-interactive defaults)** — apply, and record each decision + rationale in the evolution log:
- Case A → **keep** the skill-context rule (safe: priority guarantees the complete version); log the removal recommendation for human review.
- Case B → **keep** the skill-context rule (project experience wins by priority); log the conflict prominently for human review.
- Case C → **rewrite** the skill-context rule to include both unique parts (the recommended resolution when parts are sequential/dependent); if the parts are genuinely independent, keep skill-context and log the warning about the base's unique parts.

Apply all decisions before Step 5 — they determine the actual skill-context state for gap analysis.

### Step 5 — Analyze gaps

**First:** re-read skill-context files modified in Step 4 — do NOT use the Step 0.2 version, it is outdated. For each skill, consider the base SKILL.md AND its **current** skill-context. A gap exists only if NEITHER source covers it.

**5.1 Patch-driven gaps (prevention-point-exhaustive)**

Iterate the Prevention Point Registry. For each row × each target skill:
1. Check whether the base SKILL.md covers this **specific** prevention action.
2. Check whether skill-context has a rule covering this **specific** action.
3. A prevention point is "covered" ONLY when a rule addresses the specific action described — not merely when the patch filename appears in a Source field.

**Common trap — Source reference ≠ full coverage:** `Source: <patch-filename>` in a rule means ONE rule was derived from that patch, not that ALL its prevention points are covered. Always verify rule **content** against each prevention point individually.

**Verification:** after the scan, count total / covered / uncovered prevention points. Uncovered pairs (prevention_point, skill) become inputs for Step 6. In incremental mode counts represent this run's patch set.

**5.2 Tech-stack gaps** — skills reference generic patterns but the project uses a specific framework/language/ORM? → framework-specific guidance, matching examples, ORM-specific patterns.

**5.3 Convention gaps** — the project has a specific error-handling pattern, logger, or file structure the skills should enforce/reference/follow.

### Step 6 — Generate improvements

For each gap, create a concrete improvement. Quality rules:
- **One prevention point = one rule.** Never merge independent prevention items into a vague summary.
- **Preserve concrete formats and patterns** from patches verbatim — do NOT paraphrase specifics into vague descriptions.
- Every improvement traceable to a patch, convention, or tech-stack fact.
- No generic advice — only project-specific enhancements.
- Minimal and focused — add, don't replace; preserve existing skill structure.

### Step 7 — Present & apply

**7.1 Present improvements** using the evolution report format in `references/FORMATS.md`. Each improvement MUST state its target file path explicitly: **skill-context** (`.hermes-dev/skill-context/<skill-name>/SKILL.md`) for `aif-*` skills, **SKILL.md direct edit** only for custom/non-aif skills, or the exact nested path (e.g. `templates/…`) inside a custom skill directory.

**Interactive sessions:** ask — "apply all" / "let me pick" (batches of up to 4, Apply/Skip each) / "just save report" (no changes, STOP). Do NOT apply anything until answered.

**Kanban workers:** apply ALL evidence-backed improvements (that is the job); anything uncertain or not traceable to evidence is listed in the evolution log as "proposed, not applied" instead of being guessed in.

**7.2 Apply approved improvements**

For a built-in `aif-*` skill:
1. `mkdir -p .hermes-dev/skill-context/<skill-name>`
2. If the skill-context file doesn't exist — create it from the context file template (`references/FORMATS.md`).
3. If it exists — read it first, then per improvement: **update** an existing rule on the same topic (strengthen wording, extend its Source list, adjust severity based on new evidence), **add** a new rule when nothing covers the topic, or **merge** narrow rules into one broader rule (allowed only if all prevention points are preserved).
4. Update the `> Last updated:` and `> Based on:` header lines.
5. **NEVER edit files inside `~/.hermes/skills/aif-*/`.**
6. If after all changes (including stale-rule removals) a skill-context file has no rules left (header only), delete the file and its directory (if empty).
7. Update headers of skill-context files affected only by stale-rule removals too.

For a custom/project skill (not `aif-*`): edit its `SKILL.md` directly.

**All skill-context files MUST be written in English**, regardless of the user's language or the patches' language — they are consumed by AI agents; English ensures consistent interpretation.

**7.3 Save the evolution log**

`mkdir -p .hermes-dev/evolution` and write `.hermes-dev/evolution/YYYY-MM-DD-HH.mm.md` per the evolution log template (`references/FORMATS.md`), including all non-interactive decisions from Steps 4 and 7.1.

Then update the cursor. Definitions: "New patches processed" = patches with filename `>` `last_processed_patch` (first run: the full list; overlap patches never count). "Improvements applied" = at least one approved improvement written to disk.

Cursor rules:
1. No new patches processed → cursor unchanged.
2. New patches processed and improvements applied → advance the cursor to the newest New-patch filename.
3. New patches processed but nothing applied → do NOT advance by default (allows reruns — LLMs may miss prevention points). Interactive sessions may ask whether to advance anyway; workers keep the cursor unchanged and note it in the log.
4. Execution failed before changes were finalized → do not advance.

### Step 8 — Suggest next actions

Report: skills improved, improvements applied, then recommend: (1) run `aif-review` on recent code to verify the improvements, (2) rerun `aif-evolve` after 5–10 more fixes, (3) if a pattern keeps recurring, create a dedicated skill via `aif-skill-generator`.

## Completion & ownership

- **Primary ownership:** `.hermes-dev/skill-context/*`, `.hermes-dev/evolution/*.md`, `.hermes-dev/evolution/patch-cursor.json`. Treat roadmap/rules/research/plan artifacts as read-only context unless explicitly asked.
- **Kanban completion:** complete the task with evidence — evolution log path, patches processed (new/overlap), improvements applied per skill, stale-rule decisions taken. Block only for real reasons (patches dir unreadable, target skill missing, no access to the workspace).
- Interactive sessions: after evolution, suggest `/clear` or `/compact` — context is heavy after patch analysis.

## Rules

1. **Traceable** — every improvement links to a patch, convention, or tech fact.
2. **Minimal** — add rules to skill-context, don't rewrite base skills.
3. **Reversible** — interactive: user approves before apply; workers: every applied change is recorded in the evolution log.
4. **Cumulative** — each evolution builds on previous ones.
5. **No hallucination** — only improvements backed by evidence.
6. **Preserve structure** — never change base skill workflow, only enrich via skill-context.
7. **Skill-context only** — all improvements for `aif-*` skills go to `.hermes-dev/skill-context/`, never to `~/.hermes/skills/aif-*/`. No exceptions.
8. **English only** — all skill-context files in English.
9. **No generic advice** — "write clean code" is not an improvement.
10. **No new skills** — suggest `aif-skill-generator` instead.
11. **No losing coverage** — remove rules only when stale (Steps 3–4); merges must preserve all prevention points.
12. **Installed only** — do not evolve skills not present in `~/.hermes/skills/`.
13. **Ownership boundary** — this skill owns `.hermes-dev/evolution/*` and `.hermes-dev/skill-context/*` only.

## Example

```
evolve fix

→ Found 6/10 patches tagged #null-check
→ Improvement for aif-fix (2 rules):
  Target: .hermes-dev/skill-context/aif-fix/SKILL.md
  1. "PRIORITY CHECK: Look for optional/nullable fields accessed
      without null guards. This is the #1 source of bugs in this project."
  2. "When fixing nullable relation errors, check ALL usages of that
      relation in the same file — same bug often repeats nearby."
```
