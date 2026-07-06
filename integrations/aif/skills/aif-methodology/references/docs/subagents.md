[← Reflex Loop](loop.md) · [AIF methodology](../../SKILL.md) · [Core Skills →](skills.md)

> Ported from lee-to AI Factory `docs/subagents.md`. Adaptations: the 19 Claude subagents are
> installed **globally** in `~/.claude/agents/` (lee-to installs them project-locally into
> `.claude/agents/`); delegation is gated by `use_subagents` (task → board → `kanban.use_subagents`
> config); the Codex TOML bundle and the installer/tracking machinery are not ported.

# Subagents

The Hermes port ships the full lee-to Claude bundle — **19 subagents** — as markdown agent files
in `~/.claude/agents/`, near-verbatim (Handoff MCP / `HANDOFF_MODE` references removed, paths
mapped to the Hermes canon, frontmatter `tools`/`model`/`isolation`/`maxTurns`/`skills` preserved).

Whether they are used at all is controlled by the delegation mode:
**subagents mode** (`use_subagents=true`, the department default — resolution: per-task
`use_subagents` / CLI `--delegation` → board `board.json` → `kanban.use_subagents` config) spawns
them via the Agent tool; **skills mode** executes the same steps inline in the worker session.

> Not ported from lee-to: the Codex CLI TOML agent bundle (`.codex/agents/` + managed
> `.codex/config.toml`), per-project `installedAgentFiles`/`managedAgentFiles` tracking, and the
> `ai-factory init/update` install/refresh flows. Hermes runs one runtime (Claude-family workers);
> other-model support goes through Hermes model routing, not runtime-specific agent files.

## Why This Exists

The subagents serve six narrow purposes:
- splitting `aif-loop` into small, single-responsibility roles so the Reflex Loop stays
  predictable, cheaper to run, and easier to reason about
- one planning specialist that runs `aif-plan` + `aif-improve` as a local critique/refinement loop
  before implementation (`plan-polisher`)
- one planning coordinator that iteratively launches the specialist until the plan passes critique
  or the iteration budget is exhausted (`plan-coordinator`)
- one implementation coordinator that parses plan dependency graphs, implements single tasks
  directly with quality sidecars, and dispatches independent tasks in parallel via isolated
  workers (`implement-coordinator`)
- background execution sidecars for quality gates during implementation

The intended benefit:
- keep noisy phase work out of the main conversation/worker context
- separate writer roles from judge roles
- use cheaper models for prep work and stronger models for evaluation/refinement
- make each phase return a strict contract instead of free-form reasoning

If you edit these files manually, reload them in the target runtime (`/agents` in Claude Code;
kanban workers pick up the files on the next dispatch).

## Current Bundled Agents

All in `~/.claude/agents/` (global):

| Agent | Purpose | Model | Tools |
|---|---|---|---|
| `plan-coordinator` | iteratively launch `plan-polisher` in a critique→improve loop until the plan passes or the iteration budget is exhausted. Defaults to `full` planning when the caller did not choose a mode. **Coordinator role** | `inherit` | `Agent(plan-polisher), Read, Glob, Grep, Bash` |
| `implement-coordinator` | parse plan dependency graph, implement single tasks directly with quality sidecars, dispatch `implement-worker` workers for parallel tasks, merge results. **Coordinator role** | `inherit` | `Agent(implement-worker, best-practices-sidecar, commit-preparer, docs-auditor, review-sidecar, security-sidecar, rules-sidecar), Read, Write, Edit, Glob, Grep, Bash` |
| `implement-worker` | isolated worktree worker for parallel task execution — implements one task, runs local quality checks, returns results to coordinator | `inherit` | `Read, Write, Edit, Glob, Grep, Bash` |
| `plan-polisher` | create or refresh an `aif-plan` artifact, run one local critique+refine cycle, and return whether another iteration is needed | `inherit` | `Read, Write, Edit, Glob, Grep, Bash` |
| `best-practices-sidecar` | background read-only best-practices audit for current implementation scope | `inherit` | `Read, Glob, Grep` |
| `commit-preparer` | background read-only commit preparation sidecar | `sonnet` | `Read, Glob, Grep` |
| `docs-auditor` | background read-only documentation drift sidecar | `sonnet` | `Read, Glob, Grep` |
| `review-sidecar` | background read-only code review sidecar | `inherit` | `Read, Glob, Grep` |
| `security-sidecar` | background read-only security audit sidecar | `inherit` | `Read, Glob, Grep` |
| `rules-sidecar` | background read-only project rules sidecar (`aif-rules-check`) | `inherit` | `Read, Glob, Grep` |
| `loop-orchestrator` | decide the next loop phase from `run.json` state | `sonnet` | `Read, Glob, Grep` |
| `loop-planner` | build a short 3-5 step iteration plan | `haiku` | `Read, Glob, Grep` |
| `loop-producer` | generate the current markdown artifact | `inherit` | `Read, Write, Edit` |
| `loop-evaluator` | return strict pass/fail JSON against active rules | `inherit` | `Read, Glob, Grep` |
| `loop-critic` | translate failed rules into minimal fix instructions | `sonnet` | `Read` |
| `loop-refiner` | apply minimal fixes to the artifact | `inherit` | `Read, Write, Edit` |
| `loop-test-prep` | prepare lightweight test-oriented checks | `haiku` | `Read, Glob, Grep` |
| `loop-perf-prep` | prepare latency/RPS/perf checks | `haiku` | `Read, Glob, Grep` |
| `loop-invariant-prep` | prepare invariant and consistency checks | `haiku` | `Read, Glob, Grep` |

## How `plan-polisher` and `plan-coordinator` Fit

`plan-polisher` is not part of `aif-loop`. It is a self-contained planning worker that:
- runs an `aif-plan`-compatible pass directly inside the subagent
- defaults to the richer `full` planning contract unless the caller explicitly asks for `fast`
- performs local two-pass exploration (quick reconnaissance + deeper analysis) to cover the same
  discovery surface that `aif-plan` normally delegates to Explore subagents
- critiques the generated plan against implementation-readiness criteria
- applies at most one `aif-improve`-compatible refinement pass
- returns `needs_further_refinement: yes/no` to the caller

To stay compatible with Claude Code subagent constraints, it does **not** try to spawn nested
workers. When the injected skill instructions mention delegated exploration, the agent replaces
that with direct `Read`/`Glob`/`Grep`/`Bash` work inside the same context.

`plan-coordinator` sits above `plan-polisher` and needs a context that can spawn subagents
(a kanban worker session or a top-level `claude --agent plan-coordinator` session — see
[Top-Level Agent Sessions](#top-level-agent-sessions)).

It automates the iterative refinement loop:

1. Launch `plan-polisher` to create the initial plan, critique it, and apply one improvement pass.
2. Check the result: if `needs_further_refinement: yes`, launch `plan-polisher` again to critique
   and improve the existing plan.
3. Repeat until the plan passes critique, the iteration budget is exhausted (default: 3), or
   stagnation is detected (2 consecutive iterations with no material change).

### Configuration

Both agents accept `tests` and `docs` parameters that control whether the generated plan includes
testing and documentation tasks:

| Parameter | Default | Values | Description |
|-----------|---------|--------|-------------|
| `tests`   | `infer` | `yes`, `no`, `infer` | Include test tasks in the plan |
| `docs`    | `infer` | `yes`, `no`, `infer` | Include documentation tasks in the plan |

When set to `infer` (the default), `plan-polisher` auto-detects from the project structure:
- **tests** → `yes` if the project has a test suite (`tests/`, `__tests__/`, `*.test.*`,
  `*.spec.*`, test config files)
- **docs** → `yes` if the project has documentation infrastructure (`docs/`, structured
  `README.md`, docstring conventions)

Explicit values from the caller always take priority over inference.

### Plan-quality parity guard

(lee-to tracked this as issue #78.) The regression to guard against:
- use a straightforward task such as bootstrapping a Go project
- compare the subagent path (`plan-coordinator → plan-polisher`) with the inline path
  (`aif-plan` → `aif-improve` in skills mode)
- fail the contract if the subagent path systematically misses obvious setup work, weakens
  dependencies, or adds irrelevant implementation tasks that the inline path does not need

Judged on practical plan quality: richer defaults must not silently fall back to `fast`; local
exploration must still cover reconnaissance plus deeper analysis even without nested workers;
documentation must not promise stronger guarantees than the runtime actually ships.

## How `implement-coordinator` Fits

`implement-coordinator` is the execution-side companion to `plan-coordinator`. It needs a context
that can spawn subagents.

It combines coordination and implementation in one agent:

- **Single-task layers**: implements the task directly within the coordinator, using quality
  sidecars (`review-sidecar`, `security-sidecar`, `rules-sidecar`, `best-practices-sidecar`,
  `docs-auditor`, `commit-preparer`) as background workers. This avoids isolation overhead and
  gives full sidecar coverage.
- **Parallel-task layers**: dispatches `implement-worker` workers concurrently, one per task. Each
  worker gets its own worktree so file edits cannot collide. Workers run local quality checks
  (no sidecars — subagents cannot spawn children).

This design eliminates lee-to's previous `implementer` / `implementer-isolation` layer, which had
a structural problem: when spawned as subagents of the coordinator, they could not spawn their own
sidecar subagents. By merging implementation logic into the coordinator itself, single-task
execution gets real sidecar support, and parallel execution stays cleanly isolated.

Workflow:

1. Parse the active plan and build a dependency graph from `(depends on X, Y)` annotations.
2. Identify layers of independent tasks — tasks whose dependencies are all satisfied.
3. If a layer has multiple tasks, launch one `implement-worker` per task concurrently.
4. If a layer has a single task, implement it directly with sidecar support.
5. After each layer completes, merge worktree results, run verification, and advance to the next layer.
6. Commits are handled centrally by the coordinator, not by individual workers.

Safety constraints:
- maximum 4 parallel workers per layer
- merge conflicts cause an immediate stop (interactive: prompt the user; kanban worker:
  `kanban_block` with the conflict details)
- 2 consecutive layer failures stop the entire run
- workers are forbidden from creating commits

This agent is useful when the plan has clearly independent tasks. For simple linear plans where
every task depends on the previous one, it falls back to sequential execution automatically.

### Plan annotation

The coordinator treats the plan file as a live status document and keeps it updated throughout
execution:

1. **Before work starts** — after parsing the dependency graph, the coordinator adds
   `<!-- parallel: tasks N, M -->` comments above groups of independent tasks. This makes the
   dispatch plan visible before any code is written.
2. **When dispatching** — each task's checkbox changes from `[ ]` to `[~]` with an
   `<!-- in-progress -->` marker, so it is clear which tasks are currently in flight.
3. **After completion** — successful tasks become `[x]`, failed tasks become `[!]` with a
   `<!-- failed: reason -->` marker.

Example plan during execution:

```markdown
### Phase 1: Setup
<!-- parallel: tasks 1, 2 -->
- [x] Task 1: Create User model
- [~] Task 2: Add authentication types <!-- in-progress -->

### Phase 2: Core
- [ ] Task 3: Implement password hashing (depends on 1, 2)
- [ ] Task 4: Create auth service (depends on 3)
```

This gives crash recovery — if the session dies mid-run, the plan file shows exactly which tasks
completed, which were in flight, and which are still pending.

### Which One To Use

| Situation | Preferred agent | Why |
|---|---|---|
| You want a polished plan without manual re-runs | `plan-coordinator` | Iterates critique→improve automatically until the plan is ready |
| Quick one-shot plan that you will review yourself | `plan-polisher` (as subagent) | Single cycle, less overhead |
| Plan already exists, ready to implement | `implement-coordinator` | Skips planning, goes straight to execution |
| Any implementation task (single or parallel) | `implement-coordinator` | Handles both modes — direct execution for single tasks, isolation workers for parallel |
| End-to-end from idea to code | `plan-coordinator` then `implement-coordinator` | Run sequentially — a single combined agent is impractical due to skill/prompt overload |
| Delegation disabled (`use_subagents=false`) | none — skills mode | The role skill executes the same steps inline |

## Quality Sidecars

`best-practices-sidecar`, `commit-preparer`, `docs-auditor`, `review-sidecar`, `security-sidecar`,
and `rules-sidecar` exist for the case where an orchestrating context can legally delegate:
- all are `background: true`
- all are read-only
- all report concise blocker-focused findings back to `implement-coordinator`

This keeps noisy review, security, docs-drift, commit-analysis, and maintainability analysis out
of the main coordinator context.

(lee-to's `HANDOFF_SKIP_REVIEW=1` review-family bypass is not ported — in the Hermes pipeline
review/verify are separate stages that cannot be skipped by env var.)

`best-practices-sidecar`, `review-sidecar`, `security-sidecar`, and `rules-sidecar` use a
structured verdict contract so the coordinator can consume their results predictably:
`Verdict: PASS|WARN|FAIL`, `Blocking findings:`, `Non-blocking notes:`, and `Evidence:`.
`docs-auditor` and `commit-preparer` keep their JSON contracts because they return routing data
rather than gate findings.

The loop prep workers are also good background candidates and are configured that way:
- `loop-test-prep`
- `loop-perf-prep`
- `loop-invariant-prep`

They are read-only, parallel by design, and produce short structured outputs that do not need user
interaction.

## How They Fit Into `aif-loop`

The loop has six logical phases:

1. `PLAN`
2. `PRODUCE`
3. `PREPARE`
4. `EVALUATE`
5. `CRITIQUE`
6. `REFINE`

The subagents map onto those phases like this:

| Loop phase | Subagent |
|---|---|
| `PLAN` | `loop-planner` |
| `PRODUCE` | `loop-producer` |
| `PREPARE` | `loop-test-prep`, `loop-perf-prep`, `loop-invariant-prep` |
| `EVALUATE` | `loop-evaluator` |
| `CRITIQUE` | `loop-critic` |
| `REFINE` | `loop-refiner` |
| routing between phases | `loop-orchestrator` |

This keeps responsibilities narrow:
- planner decides what to do next
- producer writes
- evaluator judges
- critic explains what failed
- refiner changes only what is needed
- `plan-polisher` stays outside the Reflex Loop and focuses only on plan quality
- `implement-coordinator` stays outside the Reflex Loop and focuses on implementation quality closure
- the six quality sidecars stay outside the Reflex Loop and support only the implementation
  coordinator

## Design Principles

### Read-only roles stay read-only where possible

The loop's planning, evaluation, critique, and prep roles do not need write access, so they are
intentionally constrained. Most of them also use `permissionMode: plan`, which matches Claude
Code's read-only exploration mode. `plan-polisher` and `implement-coordinator` are the exceptions
because they own end-to-end refinement of their artifacts.

### Writer roles are limited

Only `loop-producer`, `loop-refiner`, `plan-polisher`, `implement-coordinator`, and
`implement-worker` can modify content. The six quality sidecars are intentionally read-only. This
reduces the chance of accidental state drift across phases and keeps write access tied to explicit
artifact ownership.

### Cheap where possible, stronger where necessary

`haiku` is used for prep/planning roles where the output is short and structured. `sonnet` is used
for orchestration, critique, and audit roles where quality matters more. The non-loop agents
(`implement-coordinator`, `implement-worker`, `plan-polisher`) use `inherit` to match the session's
model, since they handle complex multi-skill workflows where model choice should follow the
worker's model routing.

### Output contracts are strict

Most loop agents return either:
- JSON only, for machine-consumed phases
- raw markdown only, for artifact-producing phases

That makes the overall loop easier to orchestrate and validate.

## Important Claude Code Constraints

These agents follow current Claude Code subagent behavior:

- ordinary subagents cannot spawn other subagents
- nested delegation must stay in the main flow
- subagents are selected partly from the `description` field, so descriptions should be explicit
- manual edits to `~/.claude/agents/*.md` are not always picked up until reload

Because of that, the design favors phase-specialized workers instead of deep agent trees.
`plan-polisher` runs its critique/refine cycle locally instead of trying to delegate the improve
pass again. `implement-coordinator` can spawn sidecars because it runs from a context with Agent
tool access (a kanban worker session or a top-level agent session). Its isolation workers
(`implement-worker`) run local quality passes instead of trying to spawn nested sidecars.

## Top-Level Agent Sessions

There are two fundamentally different ways to use an agent:

1. **As a subagent** — the session spawns the agent with the Agent tool. The agent runs in an
   isolated context, does its work, and returns a summary. This is the default and most common mode.
2. **As a top-level agent** — an entire Claude Code session runs as that agent via
   `claude --agent <name>`. The agent's prompt replaces the default system prompt.

The critical difference: **top-level agents can spawn subagents, ordinary subagents cannot.**
This is a hard constraint, not a convention.

In the Hermes pipeline this distinction is mostly absorbed by the worker model: a **kanban worker
session is itself top-level**, so the role skill (e.g. `aif-implement`) can spawn
`implement-coordinator` (or run coordinator logic and spawn sidecars/workers directly) when
subagents mode is enabled. The `claude --agent` commands below matter for interactive use.

### When to use a top-level agent (interactive)

- The agent needs to **coordinate other agents** (`plan-coordinator`, `implement-coordinator`)
- The agent needs to **run background sidecars** (pre-approved at launch from a top-level session)
- The workflow is the **primary purpose of the session**

### When NOT to use a top-level agent

- The work is a single self-contained task that returns a result
- The agent does not need to spawn other agents (read-only workers, evaluators, critics, refiners)
- You want the agent to run alongside normal conversation (top-level agents replace the system
  prompt)

### Quick Start (interactive sessions)

**Full workflow (plan → implement):**

```bash
# Step 1: Polish the plan
claude --agent plan-coordinator "implement user authentication with JWT"

# With explicit tests/docs control
claude --agent plan-coordinator "implement user authentication with JWT, tests: yes, docs: yes"

# Step 2: Implement it (reads the plan created in step 1)
claude --agent implement-coordinator
```

A single combined agent is not feasible — the single-responsibility constraint means planning and
implementation skills in one prompt cause the LLM to skip delegation and take shortcuts.

**Plan only / implement only:**

```bash
claude --agent plan-coordinator "@.hermes-dev/plans/feature-auth.md"   # polish an existing plan
claude --agent implement-coordinator                                   # execute the active plan
claude --agent implement-coordinator "@.hermes-dev/plans/feature-auth.md"
```

**Simple single-task implementation (no coordinator needed):** load skill `aif-implement` in a
normal session.

## See Also

- [Reflex Loop](loop.md) — the workflow the loop agents support
- [Core Skills](skills.md) — skill reference including `aif-loop`
- [Configuration](configuration.md) — the `use_subagents` resolution chain
