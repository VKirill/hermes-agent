[← Getting Started](getting-started.md) · [AIF methodology](../../SKILL.md) · [Reflex Loop →](loop.md)

> Ported from lee-to AI Factory `docs/workflow.md`, adapted to the Hermes AIF department
> (fixed `.hermes-dev/` paths, skills instead of slash commands, kanban stage machine appended).

# Development Workflow

The AIF department has two phases: **configuration** (one-time project setup) and the
**development workflow** (repeatable loop of explore → plan → improve → implement → verify →
commit → evolve).

## Project Configuration

Run once per project. Sets up context files that all workflow skills depend on.

In Hermes there is no `ai-factory init` and no `.ai-factory/config.yaml` — skills live globally in
`~/.hermes/skills/` and all artifact paths are fixed (see [Configuration](configuration.md)).
The `aif` skill bootstraps a new app folder (`~/Work/apps/<slug>/` + `.hermes-dev/` scaffold +
Hermes project) or sets up context in an existing one.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       PROJECT CONFIGURATION                             │
└─────────────────────────────────────────────────────────────────────────┘

  ┌──────────────┐      ┌──────────────┐      ┌──────────────────────────┐
  │ dev-handoff  │      │  aif worker  │      │                          │
  │ or hermes    │ ───▶ │ (kanban) or  │ ───▶ │      aif skill           │
  │ kanban       │      │ interactive  │      │   (setup context)        │
  │ create       │      │   session    │      │                          │
  └──────────────┘      └──────────────┘      │  DESCRIPTION.md (root)   │
                                              │  AGENTS.md (root)        │
                                              │  .hermes-dev/ scaffold   │
                                              └────────────┬─────────────┘
                                                           │
                                                           ▼
                                              ┌──────────────────────────┐
                                              │ aif-architecture         │
                                              │  (ARCHITECTURE.md, root) │
                                              └────────────┬─────────────┘
                                                           │
                                         ┌─────────────────┼─────────────────┐
                                         │                 │                 │
                                         ▼                 ▼                 ▼
                                  ┌───────────────┐  ┌──────────────┐  ┌─────────────┐
                                  │ aif-rules     │  │ aif-roadmap  │  │  aif-docs   │
                                  │ (optional)    │  │(recommended) │  │ (optional)  │
                                  └───────────────┘  └──────────────┘  └─────────────┘

                                  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐
                                  │ aif-dockerize │  │  aif-ci      │  │ aif-build-   │
                                  │ (optional)    │  │ (optional)   │  │  automation  │
                                  └───────────────┘  └──────────────┘  │ (optional)   │
                                                                       └──────────────┘
```

## Development Workflow

The repeatable development loop. Each skill feeds into the next, sharing context through plan files
and patches.

Path examples below are the fixed Hermes `.hermes-dev/` locations — there is no config-based
relocation. Project context files stay at the project root: `DESCRIPTION.md`, `ARCHITECTURE.md`,
`AGENTS.md`.

Optional discovery step: use `aif-explore` before planning to investigate ideas, compare options,
and clarify requirements.

Reliability gate: use `aif-grounded` when the main problem is not discovery but certainty —
high-stakes answers, changeable facts, version-sensitive behavior, or any request where the model
must refuse to guess.

If you want exploration results to survive context resets and feed directly into planning, ask
`aif-explore` to save them to `.hermes-dev/research/RESEARCH.md`.

Optional conventions step: use `aif-rules` to append or refine project-wide axioms in
`.hermes-dev/RULES.md`, or `aif-rules area:<name>` to create or update
`.hermes-dev/rules/<area>.md`. Downstream workflow skills resolve rules with the same hierarchy:
`rules/<area>.md` > `rules/base.md` > `RULES.md` (discovery is by file name — there is no config
registration step in Hermes).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       DEVELOPMENT WORKFLOW                              │
└─────────────────────────────────────────────────────────────────────────┘

   Need to think first?                         Need certainty first?
          │                                             │
          ▼                                             ▼
   ┌───────────────┐                            ┌────────────────┐
   │ aif-explore   │                            │ aif-grounded   │
   │ clarify scope │                            │ verify facts   │
   │ compare paths │                            │ reject guesses │
   └───────┬───────┘                            └────────┬───────┘
           │                                             │
           └──────────────────────┬──────────────────────┘
                                  ▼

               ┌──────────────────────────┐                         ┌──────────────┐
               │                          │                         │              │
               │    aif-plan              │                         │ aif-fix      │
               │                          │                         │              │
               │  plans saved to          │                         │ Bug fixes    │
               │  .hermes-dev/plans/      │                         │ Optional plan│
               │    <slug>.md             │                         │ With logging │
               │  (branch optional)       │                         │              │
               └────────────┬─────────────┘                         └───────┬──────┘
                            │                                               │
                            │                                               ▼
                            │                                      ┌──────────────────┐
                            │                                      │ .hermes-dev/     │
                            │                                      │   patches/       │
                            │                                      │ Self-improvement │
                            └───────────┬──────────────────────────└────────┬─────────┘
                                        │                                   │
                                        ▼                                   │
                             ┌─────────────────────┐                        │
                             │                     │                        │
                             │ aif-improve         │                        │
                             │    (optional)       │                        │
                             │                     │                        │
                             │ Refine plan with    │                        │
                             │ deeper analysis     │                        │
                             │                     │                        │
                             └──────────┬──────────┘                        │
                                        │                                   │
                                        ▼                                   │
                             ┌──────────────────────┐                       │
                             │                      │◀── skill-context  ────┘
                             │ aif-implement        │       (+limited patch fallback)
                             │ ──── error?          │
                             │  ──▶ aif-fix         │
                             │  Execute tasks       │
                             │  Commit checkpoints  │
                             │                      │
                             └──────────┬───────────┘
                                        │
                                        ├─────────────────────────────────────────────────┐
                                        │                                                 │
                                        ▼                                                 ▼
                             ┌──────────────────────────────────────┐       ┌───────────────────────────┐
                             │                                      │       │                           │
                             │ aif-verify                           │       │ aif-qa                    │
                             │    (optional)                        │       │    (optional)             │
                             │                                      │       │                           │
                             │ Check completeness                   │       │ Manual QA artifacts:      │
                             │ Build / test / lint                  │       │ → change-summary          │
                             │    ↓                                 │       │ → test-plan               │
                             │ → aif-security-checklist             │       │ → test-cases              │
                             │ → aif-review                         │       │                           │
                             │                                      │       │ .hermes-dev/qa/<slug>/    │
                             └──────────────────┬───────────────────┘       └───────────────────────────┘
                                        │
                                        ▼
                             ┌─────────────────────┐
                             │                     │
                             │ aif-commit          │
                             │                     │
                             └──────────┬──────────┘
                                        │
                        ┌───────────────┴───────────────┐
                        │                               │
                        ▼                               ▼
                   More work?                        Done!
                   Loop back ↑                          │
                                                        ▼
                                             ┌─────────────────────┐
                                             │                     │
                                             │ aif-evolve          │
                                             │                     │
                                             │ Reads new patches + │
                                             │ project context     │
                                             │       ↓             │
                                             │ Improves skills     │
                                             │                     │
                                             └─────────────────────┘

```

## When to Use What?

| Skill | Use Case | Creates Branch? | Creates Plan? |
|-------|----------|-----------------|---------------|
| `aif-explore` | Discovery, option comparison, and requirements clarification before planning | No | No (optional `.hermes-dev/research/RESEARCH.md` on request) |
| `aif-grounded` | Evidence-only answers, strict verification, and high-stakes questions where guessing is unacceptable | No | No |
| `aif-roadmap` | Strategic planning, milestones, long-term vision | No | `.hermes-dev/plans/ROADMAP.md` |
| `aif-rules` | Capture project conventions or add area-specific rules before planning and implementation | No | No (`.hermes-dev/RULES.md` or `.hermes-dev/rules/<area>.md`) |
| `aif-plan` | Features, stories, epics — all plans | Optional (full mode may create a branch/worktree) | `.hermes-dev/plans/<slug>.md` |
| `aif-improve` | Refine plan before implementation | No | No (improves existing) |
| `aif-loop` | Iterative generation with quality gates and phase-based cycles | No | No (uses `.hermes-dev/loop/`) |
| `aif-reference` | Create knowledge refs from URLs/docs for AI agents | No | No (`.hermes-dev/reference/`) |
| `aif-distillation` | Turn books, docs, folders, or URLs into one reusable Agent Skill or a split set of focused skills | No | No |
| `aif-fix` | Bug fixes, errors, hotfixes | No | Optional (`.hermes-dev/fixes/FIX_PLAN.md`) |
| `aif-rules-check` | Standalone read-only rules compliance gate for staged work, working tree, or a git ref | No | No (reads existing rules and optional plan context) |
| `aif-verify` | Post-implementation quality check | No | No (reads existing) |
| `aif-qa` | Manual QA for a feature/fix: change summary → test plan → test cases | No | `.hermes-dev/qa/<branch-slug>/*.md` |
| `aif-qa-check` | Execute QA cases manually or through automated agent checks | No | `.hermes-dev/qa/<branch-slug>/qa-check.md`; agent mode also maintains `.hermes-dev/qa/agent-context.md` and `agent-history.md` |
| `aif-archive` | Archive completed plans and trim closed roadmap milestones | No | `.hermes-dev/archive/plans/*.md`, `.hermes-dev/archive/roadmap/*.md` |

Note on plan modes: lee-to distinguishes `fast` (single `PLAN.md`, no branch) from `full`
(named plan + optional branch). In Hermes both save under `.hermes-dev/plans/<slug>.md`; the
fast/full distinction only affects question depth and branch creation, not the plan location.

`aif-qa change-summary` normally derives context from git diffs. When git is unavailable or the
target/base refs cannot be resolved locally or through `origin/<base>`, it uses manual change
context instead of failing on git commands (interactive: asks; worker: reads it from the task body
or blocks with the exact missing input). `aif-qa-check` consumes the resulting `test-cases.md`;
human mode asks for one result at a time, and agent mode uses the appropriate execution surface for
each case: browser, CLI, API, automated tests, or file/document checks. Browser/UI cases still
require live browser execution (Playwright MCP or an in-app browser when available); non-browser
cases are not blocked merely because browser automation is unavailable. Agent mode reads
`agent-context.md` and `agent-history.md` first, records only reusable non-sensitive cross-QA facts
in those root-level files, and offers human-mode continuation only for human-verifiable blocked
cases. Run-specific details stay in branch-specific `qa-check.md`. QA check results are bound to
the tested commit plus worktree digest (or a manual build identifier when git is unavailable), plus
source/case digests, so stale passes are not counted after the branch, dirty working tree, or test
cases change.

## Artifact Ownership and Context Gates

Ownership is skill-scoped to avoid conflicting writers:

| Skill                                   | Primary artifact ownership                                                      | Notes                                                     |
|-----------------------------------------|----------------------------------------------------------------------------------|-----------------------------------------------------------|
| `aif`                                   | `DESCRIPTION.md`, setup `AGENTS.md` (project root)                               | invokes `aif-architecture` for the architecture file      |
| `aif-architecture`                      | `ARCHITECTURE.md` (project root)                                                 | may update architecture pointer in DESCRIPTION/AGENTS     |
| `aif-roadmap`                           | `.hermes-dev/plans/ROADMAP.md`                                                   | `aif-implement` may mark completed milestones             |
| `aif-rules`                             | `.hermes-dev/RULES.md`, `.hermes-dev/rules/<area>.md`                            | top-level axioms plus area-rule files                     |
| `aif-plan`                              | `.hermes-dev/plans/<slug>.md`                                                    | `aif-improve` refines existing plans                      |
| `aif-explore`                           | `.hermes-dev/research/RESEARCH.md`                                               | all other artifacts are read-only in explore mode         |
| `aif-reference`                         | `.hermes-dev/reference/*`, `.hermes-dev/reference/INDEX.md`                      | knowledge references from external sources                |
| `aif-distillation`                      | `~/.hermes/skills/` by default, or `--path <directory>` as an output root        | distilled skills from explicit source material            |
| `aif-fix`                               | `.hermes-dev/fixes/FIX_PLAN.md`, `.hermes-dev/patches/*.md`                      | bug-fix learning loop artifacts                           |
| `aif-evolve`                            | `.hermes-dev/evolution/*.md`, `.hermes-dev/evolution/patch-cursor.json`, `.hermes-dev/skill-context/*` | skill-context overrides + evolution logs + cursor state   |
| `aif-qa`                                | `.hermes-dev/qa/<branch-slug>/change-summary.md`, `test-plan.md`, `test-cases.md` | derived branch slug as subdirectory (see aif-qa SKILL.md) |
| `aif-qa-check`                          | `.hermes-dev/qa/<branch-slug>/qa-check.md`, `.hermes-dev/qa/agent-context.md`, `agent-history.md` | executes `aif-qa` test cases; source QA artifacts stay read-only; agent context/history are reusable automated-QA memory |
| `aif-archive`                           | `.hermes-dev/archive/plans/*.md`, `.hermes-dev/archive/roadmap/*.md`             | moves completed plans from `.hermes-dev/plans/`; trims closed milestones from the roadmap |
| `aif-rules-check`                       | read-only context by default                                                     | standalone rules gate; no default context-file writes     |
| `aif-commit` `aif-review` `aif-verify`  | read-only context by default                                                     | gate and report, no default context-file writes           |

Context-gate defaults for `aif-commit`, `aif-review`, `aif-verify`:
- Check architecture, roadmap, and rules alignment as read-only context.
- Missing optional files (`ROADMAP.md`, `RULES.md`) are `WARN`, not immediate failures.
- In strict verification, clear architecture/rules violations and clear roadmap mismatch are blocking failures.
- `aif-rules-check` is the standalone rules-only companion and uses human `PASS` / `WARN` / `FAIL` labels.
- `aif-verify`, `aif-review`, `aif-security-checklist`, and `aif-rules-check` emit the final
  machine-readable `gate_result` JSON block with lowercase `pass` / `warn` / `fail` status values,
  passed via `kanban_complete` (pass/warn) or `kanban_block` (fail). See [Quality Gates](quality-gates.md).

## Workflow Skills

These skills form the development pipeline. Each one feeds into the next.
(Compact summaries — full details per skill in [Core Skills](skills.md).)

### `aif-explore [topic or plan name]` — discovery before planning

Thinking-partner mode for exploring ideas, constraints, and trade-offs without implementing code.
Reads DESCRIPTION.md, ARCHITECTURE.md, rules, and research artifacts plus active plan files for
context. If you want the context to persist across sessions, save it to
`.hermes-dev/research/RESEARCH.md`. When direction is clear, transition to `aif-plan`.

### `aif-grounded [question or task]` — certainty before action

Reliability-gate mode for evidence-backed answers. Use it when the task is already clear but the
answer must be strictly verified: high-stakes requests, version-sensitive facts, current-state
questions, or any prompt that says "no assumptions". Unlike `aif-explore`, it is not for
brainstorming; it either answers from evidence with `Confidence: 100/100` or stops with
`INSUFFICIENT INFORMATION` and says what is missing.

### `aif-roadmap [check | vision]` — strategic planning

High-level project planning. Creates `.hermes-dev/plans/ROADMAP.md` — a strategic checklist of
major milestones (not granular tasks). Use `check` to automatically scan the codebase and mark
milestones that appear done. `aif-implement` also checks the roadmap after completing all tasks.

### `aif-plan <description>` — plan the work

Analyzes requirements, explores the codebase for patterns, creates tasks with dependencies, and
saves the plan to `.hermes-dev/plans/<slug>.md`. If the user supplied a planning request, it is
saved verbatim in `## Original Request`; downstream rewrites must preserve it exactly. If
`RESEARCH.md` influences the plan, a `## Research Context` section with a source revision is
embedded as the committed requirements snapshot. For 5+ tasks, includes commit checkpoints.
Step 3.5 bootstraps brand-new apps (folder + `.hermes-dev/` + Hermes project). In the kanban
pipeline the planner never implements — it hands off to `aif_implementer`.

### `aif-improve [--list] [+check] [@plan-file] [prompt]` — refine the plan

Second-pass analysis. Finds missing tasks (migrations, configs, middleware), fixes dependencies,
removes redundant work, and surfaces useful-but-out-of-scope tasks in a separate "Out of scope"
report section without persisting them. Preserves `Original Request` verbatim and warns on
research drift (`WARN [research-drift]`) instead of silently applying newer research. `--list` is a
read-only discovery mode. Optional `+check` runs a single fresh-context validator subagent on the
refinements, drops invented items, and appends `Hidden/Adjusted by +check` counters.

### `aif-loop [new|resume|status|stop|list|history|clean] [task or alias]` — iterative quality loop

Runs a strict Reflex Loop with 6 phases: PLAN → PRODUCE||PREPARE → EVALUATE → CRITIQUE → REFINE.
PRODUCE and PREPARE run in parallel (Agent tool); EVALUATE runs check groups in parallel. Before
iteration 1 it confirms success criteria and max iterations (interactive: asks; worker mode: fixes
defaults from the task text and logs them). State lives under `.hermes-dev/loop/` (`current.json`,
`<alias>/run.json`, `history.jsonl`, `artifact.md`). Stops on threshold reached, no major issues,
stagnation, or max iterations (default: 4). See [Reflex Loop](loop.md) for full contracts.

### `aif-implement` — execute the plan

Reads skill-context rules first (`.hermes-dev/skill-context/aif-implement/SKILL.md`), then uses
limited recent patch fallback when needed. Executes tasks one by one with commit checkpoints.
Plan source priority: `@plan-file` argument, then branch-based `.hermes-dev/plans/<branch>.md`,
then a single named full plan in `.hermes-dev/plans/`, then `.hermes-dev/fixes/FIX_PLAN.md`
(redirects to `aif-fix`). Docs policy after completion: `Docs: yes` → mandatory docs checkpoint
(routed via `aif-docs`), `Docs: no` or unset → `WARN [docs]` only.

When subagents mode is enabled (department default — see `kanban.use_subagents` in
[Configuration](configuration.md)), execution runs through the `implement-coordinator` subagent,
whose quality-gate sidecars include `review-sidecar`, `security-sidecar`, `rules-sidecar`
(`aif-rules-check`), and `best-practices-sidecar` after code changes. In skills mode the worker
executes the steps inline. (lee-to's `HANDOFF_SKIP_REVIEW=1` bypass has no Hermes equivalent —
review gates are separate pipeline stages here and are never silently skipped.)

### `aif-verify [--strict]` — check completeness

Goes through every task in the plan and verifies the code actually implements it. Checks build,
tests, lint, leftover TODOs, undocumented env vars, and plan-vs-code drift. Runs read-only context
gates against ARCHITECTURE.md, the roadmap, and RULES.md. If gaps are found, it suggests (or, as a
gate in the pipeline, triggers) `aif-fix`. If verification is clean, `aif-security-checklist` and
`aif-review` follow. Use `--strict` before merging to the base branch. Emits the `gate_result`
block (gate `verify`) for the workflow core.

### `aif-rules-check` — standalone rules gate

Checks only rules compliance for staged changes, working-tree changes, or a provided git ref.
Reads the resolved rules hierarchy, uses optional active plan context only to disambiguate scope,
and stays read-only. Human verdicts are `PASS` / `WARN` / `FAIL`: missing or ambiguous rules stay
`WARN`; `FAIL` is reserved for explicit hard-rule violations tied to concrete diff evidence.
Emits the `gate_result` block (gate `rules`).

### `aif-review [PR number or URL] [+check]` — code review with read-only context gates

Reviews staged changes or PR diff and reports correctness/security/performance findings. Includes
read-only architecture/roadmap/rules gate notes (`WARN` for non-blocking inconsistencies, `ERROR`
only for explicitly blocking criteria), then emits the `gate_result` block (gate `review`).
Optional `+check` runs a fresh-context validator subagent on the drafted findings: drops invented
items, rewrites partially-correct ones, may reclassify between Critical Issues and Suggestions
(rules in `aif-review` references/SEVERITY.md). The `gate_result` is rebuilt **after** filtering, so
a failing context gate keeps `status: fail` even when no Critical Issues remain.

### `aif-commit` — conventional commit with read-only context gates

Creates conventional commits from staged changes and runs read-only architecture/roadmap/rules
checks before finalizing the message. When an active plan contains `## Commit Plan`, it uses the
planned commit groups first; unmapped staged files stop the flow before staging or committing.
Hunk-level staging when a file spans multiple groups. Warning-first by default. For
`feat`/`fix`/`perf` commits, missing roadmap milestone linkage is a warning.
Push/merge without human approval is forbidden by Hermes department policy.

### `aif-fix [bug description]` — fix and learn

Two modes: **Fix now** (investigate → Canonical Regression-First Policy when needed → fix with
logging → rerun the regression check) and **Plan first** (creates `.hermes-dev/fixes/FIX_PLAN.md`
with analysis and checklist, then stops for review). Running without arguments executes an existing
fix plan and deletes only the default `FIX_PLAN.md`. Every fix creates a **self-improvement patch**
in `.hermes-dev/patches/`. In the kanban pipeline, `aif-fix` is what closes the review→fix loop:
a gate FAIL spawns a fix task (idempotency-key `fix:<id>`) linked back for re-review.

### `aif-evolve` — improve skills from experience

Reads patches incrementally using the evolve cursor
(`.hermes-dev/evolution/patch-cursor.json`), analyzes project patterns, and writes targeted rules
to `.hermes-dev/skill-context/<skill>/SKILL.md`. Closes the learning loop:
**fix → patch → evolve → better skills → fewer bugs**.

---

For full details on all skills including utility ones (`aif-docs`, `aif-dockerize`,
`aif-build-automation`, `aif-ci`, `aif-commit`, `aif-rules-check`, `aif-skill-generator`,
`aif-distillation`, `aif-reference`, `aif-security-checklist`, `aif-qa`, `aif-qa-check`),
see [Core Skills](skills.md).

## Why Spec-Driven?

- **Predictable results** — AI follows a plan, not random exploration
- **Resumable sessions** — progress saved in plan files, continue anytime
- **Commit discipline** — structured commits at logical checkpoints
- **No scope creep** — AI does exactly what's in the plan, nothing more

## Hermes stage machine

This section is Hermes-specific (no lee-to equivalent — it ports the `aif-handoff` coordinator
into the Hermes kanban core, `hermes_cli/kanban_workflow.py`).

`hermes kanban create --workflow aif` puts **one** card through the whole pipeline:

```
spec → planning → (improve) → plan_ready* → implementing → (verify) → review → done* → verified
```

- `spec` is an optional Hermes-only pre-stage (role `aif_specifier`); default entry is `planning`.
  Choose the entry stage with `--workflow-step`.
- `(improve)` runs only when `kanban.run_plan_improve` is enabled (default off);
  `(verify)` runs when `kanban.run_post_verify` is enabled (default on).
- Stages marked `*` (`plan_ready`, `done`) are **human gates**: the card waits as
  `blocked`/`needs_input` on that step. In auto mode (the default — the department is autonomous)
  they are skipped; `--human-gates` at create time restores lee-to's pausing behavior.
- `verified` is the only terminal state. In Hermes it is represented as `status=done` +
  `current_step_key=verified` — kanban statuses were not extended, so parent-gating keeps its
  meaning: a workflow card is never "done" before verification.
- Each work stage is executed by its role profile: `aif_specifier`, `aif_planner` (planning +
  improve), `aif_implementer`, `aif_verifier`, `aif_reviewer`.

Gate failures and convergence:
- `verify`/`review` FAIL is reported via `kanban_block` carrying the `gate_result` JSON
  (see [Quality Gates](quality-gates.md)). The workflow core's convergence gate
  (`evaluate_review_gate`) tracks findings by stable id across rounds (`still_blocking` /
  `resolved` / `new`).
- Decision tree: no blockers → advance; blockers and iteration < cap → rework (card returns to
  `implementing`, findings carried over); iteration ≥ cap (`kanban.max_review_iterations`,
  default 3, per-task override `max_review_iterations`) → `manual_review_required`;
  with the `closure_first` strategy, old findings resolved but NEW blockers appearing after rework
  → `manual_review_required` as well. Malformed gate output never counts as PASS.
- The convergence counter covers rework cycles of BOTH gates (verify + review) — protection
  against a verify↔implement ping-pong too.
- Every gate decision is written as an auto Review Gate Summary comment on the card.

Human actions (CLI):
- `hermes kanban approve <id>` — approve at a human gate (`plan_ready` → start implementation;
  `done` → verified).
- `hermes kanban request-changes <id> "<reason>"` — send the card back to `implementing`.
- `hermes kanban gate-action <id> <action>` — explicit action by name
  (`start_implementation`, `request_replanning`, `approve_done`, `request_changes`).
- A generic `unblock` on a workflow gate is refused — use the actions above.

## See Also

- [Reflex Loop](loop.md) — strict iterative loop contracts and state transitions
- [Core Skills](skills.md) — detailed reference for all workflow and utility skills
- [Plan Files](plan-files.md) — how plan artifacts are stored and managed
- [Quality Gates](quality-gates.md) — the machine-readable gate_result contract
- [Configuration](configuration.md) — Hermes config mapping for the workflow keys used above
