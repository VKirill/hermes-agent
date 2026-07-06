---
name: aif-loop
description: >-
  Run a strict multi-iteration Reflex Loop with phases (PLAN, PRODUCE||PREPARE, EVALUATE,
  CRITIQUE, REFINE) to improve an artifact until quality gates pass or iteration limits
  are reached. Orchestrates the loop-* subagent family when subagents mode is enabled.
  Use for iterative refinement, quality-gated generation, or "generate → critique →
  refine" loops. Port of lee-to AI Factory /aif-loop, adapted to Hermes.
tags:
  - aif
  - reflex-loop
  - iteration
  - quality-gate
  - dev-factory
---

# aif-loop — Reflex Iteration Workflow

Run a result-focused iterative loop with strict phase contracts, evaluation rules, and persistent state between sessions.

## Hermes context

- Runs as a kanban worker or interactively. **No `HANDOFF_MODE`, no `.ai-factory/config.yaml`** — loop state lives at a fixed path: **`.hermes-dev/loop/`** in the target workspace.
- **Subagent delegation:** if subagents mode is enabled (department default), spawn the `loop-*` subagent family via the Agent tool — `loop-orchestrator` (next-step routing), `loop-planner` (PLAN), `loop-producer` (PRODUCE), `loop-test-prep`/`loop-perf-prep`/`loop-invariant-prep` (PREPARE, pick the prep agents matching the active rule categories), `loop-evaluator` (EVALUATE), `loop-critic` (CRITIQUE), `loop-refiner` (REFINE). In skills mode execute the phases inline yourself.
- **Autonomous:** kanban workers do not ask questions — derive setup from the task body (Step 2 worker path) and block only for genuinely missing input. Interactive (topic/CLI) sessions confirm setup as written.

Terminology:

- **loop** = one full execution for a task alias (stored in `run.json`, identified by `run_id`)
- **iteration** = one cycle inside that loop

## Core idea

Each iteration executes 6 phases with parallel execution where possible:

1. `PLAN` - short plan for current iteration
2. `PRODUCE` - produce one `artifact.md` ← **runs in parallel with PREPARE**
3. `PREPARE` - generate check scripts and test definitions from rules ← **runs in parallel with PRODUCE**
4. `EVALUATE` - run prepared checks + content rules against artifact, score result. Uses parallel subagents for independent check groups
5. `CRITIQUE` - precise issues + fixes (only if fail)
6. `REFINE` - rewrite artifact using critique (only if fail)

```text
         PLAN
           │
    ┌──────┴──────┐
    ↓             ↓          ← parallel (Agent tool)
 PRODUCE      PREPARE
 (artifact)   (checks)
    ↓             ↓
    └──────┬──────┘
           ↓
       EVALUATE              ← parallel check execution (Agent tool)
       ┌───┼───┐
       ↓   ↓   ↓
      exec content aggregate
       └───┼───┘
           ↓
       CRITIQUE (if fail)
           ↓
       REFINE (if fail)
```

Stop when quality is good enough, no major issues remain, or iteration limit is reached.

## Persistence contract

Use exactly 3+1 files for state inside `.hermes-dev/loop/` (where `current.json` exists only while a loop is active):

```text
.hermes-dev/loop/current.json
.hermes-dev/loop/<task-alias>/run.json
.hermes-dev/loop/<task-alias>/history.jsonl
.hermes-dev/loop/<task-alias>/artifact.md
```

Do not create extra index files or per-iteration folder trees unless explicitly asked.

### File roles

- `current.json`: pointer to active loop only; delete it when loop becomes `completed`/`stopped`/`failed`
- `run.json`: single source of truth for current loop state
- `history.jsonl`: append-only event log (one JSON object per line)
- `artifact.md`: single source of truth for artifact content (written after PRODUCE and REFINE phases, never duplicated in `run.json`)

## Command modes

Parse the invocation arguments (or the kanban task body):

- `status` - show active loop status from `current.json` and stop
- `resume [alias]` - continue active loop or loop by alias
- `stop [reason]` - stop active loop with reason (`user_stop` if omitted)
- `new <task>` or no mode + task text - start new loop
- `list` - list all task aliases with status (running/stopped/completed/failed)
- `history [alias]` - show event history for a loop (default: active loop)
- `clean [alias|--all]` - remove loop files for a stopped/completed/failed loop (interactive: always confirm before deleting; workers: never clean unless the task explicitly orders it)

If no task and no active loop exists: interactive → ask for the task prompt; worker → `kanban_block` with "no loop task provided and no active loop".

## Step 0: Load context

Read these files if present in the target workspace:

- `DESCRIPTION.md` and `ARCHITECTURE.md` (project root)
- `.hermes-dev/RULES.md` (+ `.hermes-dev/rules/*`)

Use them to keep outputs aligned with project conventions.

**Read `.hermes-dev/skill-context/aif-loop/SKILL.md`** — MANDATORY if the file exists. It contains project-specific rules accumulated by `aif-evolve` from patches, codebase conventions, and tech-stack analysis.

**How to apply skill-context rules:**
- Treat them as **project-level overrides** for this skill's general instructions
- On conflict with a general rule in this SKILL.md, **the skill-context rule wins** (more specific context takes priority — same principle as nested CLAUDE.md files)
- When there is no conflict, apply both
- Do NOT ignore skill-context rules even if they seem to contradict this skill's defaults — they exist because the project's experience proved the default insufficient
- **CRITICAL:** skill-context rules apply to ALL outputs of this skill — the generated artifact, run state, and evaluation criteria. "Artifact MUST include X" / "evaluation MUST check Y" → you MUST comply.

**Enforcement:** after generating any output artifact, verify it against all skill-context rules; fix violations before presenting/saving.

## Step 0.1: Handle non-iteration commands

If command is `status`, `stop`, `list`, `history`, or `clean`, execute and stop:

- **`status`**: read `current.json`; if it exists, read the pointed `run.json` and display `alias | status | iteration | phase | current_step | last_score | updated_at`; if missing, report that no loop is active
- **`stop [reason]`**: stop active running loop only; set `run.json.status = "stopped"` and `run.json.stop.reason = <reason or "user_stop">`, append `stopped` event to `history.jsonl`, then delete `current.json` and exit
- **`list`**: scan `.hermes-dev/loop/`, read each `run.json`, display table of `alias | status | iteration | last_score | updated_at`
- **`history [alias]`**: read `history.jsonl` for the alias (or active loop), display formatted event timeline
- **`clean [alias|--all]`**: show what will be deleted and require explicit confirmation (interactive only — workers refuse unless the task explicitly orders the clean). Only clean stopped/completed/failed loops — refuse to clean running loops. Update `current.json` if needed.

## Step 1: Initialize or resume loop

### 1.1 Ensure directories

```bash
mkdir -p .hermes-dev/loop
```

### 1.2 Alias and IDs (new loop)

Generate:

- `task_alias`: lowercase hyphen slug (3-64 chars)
- `run_id`: `<task_alias>-<yyyyMMdd-HHmmss>`

### 1.3 Write `current.json`

```json
{
  "active_run_id": "courses-api-ddd-20260218-120000",
  "task_alias": "courses-api-ddd",
  "status": "running",
  "updated_at": "2026-02-18T12:00:00Z"
}
```

### 1.4 Write initial `run.json`

```json
{
  "run_id": "courses-api-ddd-20260218-120000",
  "task_alias": "courses-api-ddd",
  "status": "running",
  "iteration": 1,
  "max_iterations": 4,
  "phase": "A",
  "current_step": "PLAN",
  "task": {
    "prompt": "OpenAPI 3.1 spec + DDD notes + JSON examples",
    "ideal_result": "..."
  },
  "criteria": {
    "name": "loop_default_v1",
    "version": 1,
    "phase": {
      "A": { "threshold": 0.8, "active_levels": ["A"] },
      "B": { "threshold": 0.9, "active_levels": ["A", "B"] }
    },
    "rules": []
  },
  "plan": [],
  "prepared_checks": null,
  "evaluation": null,
  "critique": null,
  "stop": { "passed": false, "reason": "" },
  "last_score": 0,
  "stagnation_count": 0,
  "created_at": "2026-02-18T12:00:00Z",
  "updated_at": "2026-02-18T12:00:00Z"
}
```

### 1.5 Resume logic

When resuming a loop:

1. Read `run.json` to get `current_step` and `iteration`
2. Read last event from `history.jsonl` to confirm consistency
3. If `run.json.current_step` indicates a phase was interrupted:
   - Re-execute from that phase (do not skip)
   - `PRODUCE_PREPARE`: always re-run both PRODUCE and PREPARE (idempotent — artifact overwrites, checks regenerate)
4. If `run.json.status` is `stopped`, `completed`, or `failed`, inform the caller and suggest `new` (for `failed` runs, also show the last `phase_error` event from `history.jsonl` so it is clear what went wrong)

## Step 2: Setup (new loop)

### Interactive setup (topic/CLI sessions — confirmation-first)

Quick mode (default) when the task prompt contains enough context to infer task type and ideal result:

1. Auto-detect task type from prompt (API spec, code, docs, config)
2. Load matching template from `references/CRITERIA-TEMPLATES.md`
3. Draft inferred rules, phase thresholds (fallback: A=0.8, B=0.9), and max iterations (default: `4`)
4. Show inferred settings as a draft summary
5. **Always ask explicit confirmation of success criteria** (rules/thresholds), even if criteria were already present in the task text
6. **Always ask explicit confirmation of max iterations**, even if an iteration count was already present in the task text
7. If the user changes either criteria or max iterations, update the draft and re-confirm both fields
8. Start iteration 1 only after both confirmations are explicit
9. If task type cannot be auto-detected (ambiguous or mixed prompt), fall through to full setup: ask concise questions — task type, ideal result definition, mandatory checks (tests, schema/contract, specific requirements), quality threshold (A/B), max iterations (default 4), what counts as a major issue — then the two explicit confirmations above

Never treat criteria or iteration limits parsed from task text as final until the user explicitly confirms both.

### Worker setup (kanban, non-interactive)

1. Auto-detect task type from the kanban task body; load the matching template from `references/CRITERIA-TEMPLATES.md`
2. Take criteria, thresholds, and max iterations from the task body when stated; otherwise defaults (A=0.8, B=0.9, max_iterations=4)
3. Add task-specific rules derived from the stated ideal result and mandatory checks
4. Record the full derived setup in `run.json.criteria` and in the `run_started` history event — this snapshot replaces interactive confirmation as the audit trail
5. Block only if the task body gives no usable task prompt / ideal result at all

Generate evaluation rules from the answers/task body: load the matching template as the starting point, add task-specific rules. Persist answers and generated rules inside `run.json.criteria` (snapshot for reproducibility).

Normalization rules before persisting:

- `run.json.max_iterations` is the single source of truth for the iteration limit
- every rule must be expanded to full RULE-SCHEMA format (`id`, `description`, `severity`, `weight`, `phase`, `check`)
- if template shorthand omitted `weight`, derive from severity (`fail`=2, `warn`=1, `info`=0)

## Step 3: Phase contracts

Before running phases, load:

- `references/PHASE-CONTRACTS.md` - strict I/O contracts for each phase
- `references/RULE-SCHEMA.md` - rule format and score calculation

### 3.1 Phases

- `PLAN` - generates iteration plan (sequential) — `loop-planner`
- `PRODUCE` - generates artifact (parallel with PREPARE) — `loop-producer`
- `PREPARE` - generates check scripts/definitions from rules + task prompt (parallel with PRODUCE) — `loop-test-prep` / `loop-perf-prep` / `loop-invariant-prep` per active rule categories
- `EVALUATE` - runs prepared checks + content rules, aggregates score (parallel check groups) — `loop-evaluator`
- `CRITIQUE` - identifies issues with fix instructions (sequential, only on fail) — `loop-critic`
- `REFINE` - applies fixes to artifact (sequential, only on fail) — `loop-refiner`

Between phases, `loop-orchestrator` decides the next step from run state, stop guards, and the last evaluation (subagents mode); in skills mode apply Step 4/Step 5 routing yourself.

### 3.2 Parallel execution model

Two levels of parallelism via the Agent tool (subagents mode):

1. **Inter-phase**: PRODUCE and PREPARE run as parallel subagents after PLAN completes. Both depend only on PLAN output.
2. **Intra-phase**: EVALUATE spawns parallel subagents for independent check groups (executable checks via Bash, content rules via Read/Grep). Aggregates results into final score.

### 3.3 Phase output format

Each phase produces its defined output (see PHASE-CONTRACTS.md). No envelope wrapping. No router output.

## Step 4: Iteration execution

For each iteration:

1. Set `run.json.current_step = "PLAN"`, run PLAN phase
2. Set `run.json.current_step = "PRODUCE_PREPARE"`, launch both in parallel (subagents mode) or sequentially inline (skills mode):
   - PRODUCE (`loop-producer`): generates artifact → writes to `artifact.md`
   - PREPARE (prep agents): generates check scripts/definitions from rules + plan
   - Wait for both to complete
3. Set `run.json.current_step = "EVALUATE"`, run EVALUATE phase:
   - Spawn parallel subagents for independent check groups:
     - Executable checks (compile, lint, tests) → subagent with Bash
     - Content rules (structure, completeness, style) → subagent with Read/Grep
   - Aggregate results into score
4. If `passed=false`:
   - Set `run.json.current_step = "CRITIQUE"`, run CRITIQUE phase
   - Set `run.json.current_step = "REFINE"`, run REFINE phase
   - Write updated artifact to `artifact.md`
   - Increment iteration and continue
5. If `phase=A` and `passed=true`:
   - Switch to `phase=B`, activate B-level rules
   - Set `run.json.current_step = "PREPARE"`, re-run PREPARE with `phase=B` to materialize B-level checks (no PLAN/PRODUCE — artifact already passed A)
   - Set `run.json.current_step = "EVALUATE"`, run EVALUATE against the same artifact with B-level prepared checks
   - If B evaluation also passes → stop with success (`threshold_reached`)
   - If B evaluation fails → continue to CRITIQUE → REFINE, then increment iteration
6. If `phase=B` and `passed=true`:
   - Stop with success (`threshold_reached`)

### Fallback to sequential

If the Agent tool is unavailable, subagents mode is off, or subagent calls return errors, fall back to sequential inline execution: PLAN → PRODUCE → PREPARE → EVALUATE → CRITIQUE → REFINE. The loop must work without parallelism.

## Step 5: Stop conditions

Stop when any condition is met:

1. `phase=B` and `passed=true` (`reason=threshold_reached`)
2. no `fail`-severity rules failed in current evaluation (`reason=no_major_issues`) — even if score is below threshold, the artifact has no blocking issues and only `warn`/`info` remain
3. `iteration >= run.max_iterations` (`reason=iteration_limit`)
4. explicit user stop (`reason=user_stop`)
5. stagnation detected (`reason=stagnation`)

### Stagnation rule

Track score progress:

- `delta = score - last_score`
- if `delta < 0.02` and there are no severity `fail` blockers, increment `stagnation_count`
- if `stagnation_count >= 2`, stop with `stagnation`

## Step 6: Persistence writes (every step)

After each phase output:

1. Update `run.json` (including `current_step`)
2. Append event to `history.jsonl`
3. Update `current.json.updated_at`
4. Write `artifact.md` to disk after PRODUCE and REFINE phases
5. Before REFINE overwrites `artifact.md`, save a SHA-256 hash of the previous artifact in the `refinement_done` event payload as `"previous_artifact_hash"` (enables integrity verification without bloating history)

Event names: `run_started`, `plan_created`, `artifact_created`, `checks_prepared`, `evaluation_done`, `critique_done`, `refinement_done`, `phase_switched`, `iteration_advanced`, `phase_error`, `stopped`, `failed`.

`history.jsonl` example line:

```json
{"ts":"2026-02-18T12:01:10Z","run_id":"courses-api-ddd-20260218-120000","iteration":1,"phase":"A","step":"EVALUATE","event":"evaluation_done","status":"ok","payload":{"score":0.72,"passed":false}}
```

## Step 7: Post-loop

After the loop stops (any reason):

1. Display final state summary (`iteration`, `max_iterations`, `phase`, `final score`, `stop reason`)
2. If `stop reason = iteration_limit` and latest evaluation has `passed=false`, include mandatory **distance-to-success** details:
   - active phase threshold and final score
   - numeric gap to threshold (`threshold - score`, floor at `0`)
   - remaining failed `fail`-severity rule count + blocking rule IDs
   - rules progress (`passed_rules / total_rules`)
3. The final artifact stays at `.hermes-dev/loop/<alias>/artifact.md` (default). Interactive sessions may offer to copy it to a user-specified path; workers include the path in the handoff instead.
4. Suggest next skills based on artifact type:
   - API spec → `aif-plan` to implement it
   - Code → `aif-verify` to check it
   - Docs → `aif-docs` to integrate it
5. Update `run.json.status` based on stop reason, and if `current.json` points to this loop, delete `current.json` (no active loop remains):

| Stop reason | Status |
|-------------|--------|
| `threshold_reached` | `completed` |
| `no_major_issues` | `completed` |
| `user_stop` | `stopped` |
| `iteration_limit` | `stopped` |
| `stagnation` | `stopped` |
| `phase_error` | `failed` |

**Kanban handoff:** `threshold_reached`/`no_major_issues` → `kanban_complete` with the final summary + artifact path. `iteration_limit`/`stagnation` with remaining `fail`-severity blockers → `kanban_block` with the distance-to-success block (never silently complete a loop that still has blocking rules failing). `phase_error` → `kanban_block` with the last `phase_error` event.

## Step 8: Response format

Show a compact summary after each iteration — do NOT dump full `run.json` or `artifact.md` content into the conversation. The artifact is already on disk; duplicating it wastes context.

### Iteration summary format

```text
── Iteration {N}/{max} | Phase {A|B} | Score: {score} | {PASS|FAIL} ──
Plan: {1-line summary of plan focus}
Hash: {first 8 chars of artifact SHA-256}
Changed: {list of added/modified sections, or "initial generation"}
Failed: {comma-separated rule IDs, or "none"}
Warnings: {comma-separated rule IDs, or "none"}
Artifact: .hermes-dev/loop/<alias>/artifact.md
```

- `Hash` — lets the reader verify which version they're looking at without reading the full artifact
- `Changed` — shows what actually moved between iterations so regressions are visible from the summary alone

If `passed=false`, append a compact critique summary (rule ID + 1-line fix instruction per issue). Do not repeat the full artifact or full evaluation object.

When the loop terminates with `reason=iteration_limit` and `passed=false`, append a compact `distance_to_success` block to the final response.

### Full output exceptions

Show the **full artifact content** (not just summary) in these cases only:

1. **Loop termination** — the final iteration always outputs the complete artifact
2. **Phase A → B transition** — show the phase-A-passing artifact in full once at the transition boundary for visibility (B-level evaluation still runs immediately per Step 4)
3. **Explicit user request** — user asks to see the full artifact mid-loop

## Step 9: Context management

The loop generates significant context per iteration (subagent results, evaluation data, critique). After several iterations the conversation context grows large, degrading quality.

All loop state is persisted to disk — clearing context loses nothing. The `resume` command fully reconstructs state from files.

Recommend clearing context (interactive sessions) at these points: after iteration 2 (midpoint of a default 4-iteration loop), on the Phase A → B transition, and after any iteration where `iteration >= 3`. Append after the iteration summary:

```text
💡 Context is growing. Recommended: /clear, then load skill aif-loop with `resume`.
   All state is saved on disk — nothing will be lost.
```

Do not force or auto-clear — the user decides; if ignored, continue normally. Kanban workers simply rely on the persistence contract: a new worker session resumes with `resume <alias>`.

## Error recovery

### Invalid phase output

If a phase produces output that does not match its contract:

1. Log the error to `history.jsonl` with event `phase_error`
2. Retry the phase once with the same inputs
3. If retry also fails, stop the loop with `reason=phase_error` and surface the error (worker: `kanban_block`)

### Corrupted `run.json`

If `run.json` is missing or unparseable:

1. Read `history.jsonl` to reconstruct the last known state
2. Rebuild `run.json` from the most recent events (last iteration, phase, score, etc.)
3. If `history.jsonl` is also missing/empty, report it and suggest starting a new loop

## Important rules

1. `run.json` is the only source of current state truth (does NOT store artifact content)
2. `artifact.md` on disk is the single source of truth for artifact content — never duplicate it in `run.json`
3. `history.jsonl` is append-only; do not edit old events
4. Keep loop fast: short plans, targeted critique, minimal rewrites
5. Do not create extra files beyond the 3+1 persistence files
6. Evaluator must remain strict and non-creative
7. Refiner changes only what is needed to pass failed rules
8. Start simple and add complexity only when metrics show need
9. Retry failed phases exactly once before stopping
10. Use compact iteration summaries by default (Step 8). Full artifact output is allowed only in Step 8 exceptions; never dump full `run.json` into conversation
11. Recommend context clear at strategic points (Step 9) — after iteration 2, on phase transition, or when iteration >= 3
12. Never `kanban_complete` a loop that stopped with `fail`-severity rules still failing — block with distance-to-success

## Examples

```text
aif-loop new OpenAPI 3.1 spec + DDD notes + JSON examples
aif-loop resume
aif-loop resume courses-api-ddd
aif-loop status
aif-loop stop
aif-loop list
aif-loop history
aif-loop history courses-api-ddd
aif-loop clean courses-api-ddd
aif-loop clean --all
```
