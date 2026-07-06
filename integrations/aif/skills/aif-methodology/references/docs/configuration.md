[← Extensions](extensions.md) · [AIF methodology](../../SKILL.md) · [Config Reference →](config-reference.md)

> Rewritten for Hermes: lee-to's `.ai-factory/config.yaml` and `.ai-factory.json` do **not** exist
> here. This page explains where configuration actually lives in the Hermes AIF department and
> maps lee-to's config surfaces onto it. Key-by-key tables: [Config Reference](config-reference.md).

# Configuration

## Where configuration lives in Hermes

The department has four configuration surfaces, from broadest to narrowest (narrower wins):

| Surface | What it holds | Examples |
|---------|---------------|----------|
| **Hermes config** (`kanban.*` keys in the gateway config) | department-wide workflow defaults | `kanban.max_review_iterations`, `kanban.auto_review_strategy`, `kanban.run_plan_improve`, `kanban.run_post_verify`, `kanban.use_subagents` |
| **Per-board `board.json`** | board-level overrides and routing | `orchestrator_profile`, `default_assignee`, `use_subagents` |
| **Per-task columns** (kanban DB, set at create time or via CLI) | card-level overrides | `max_review_iterations`, `use_subagents` (CLI `--delegation`), `auto_mode` (CLI `--human-gates`) |
| **Fixed conventions** | everything lee-to made configurable via `config.yaml` paths | the `.hermes-dev/` layout, root context files, English artifacts |

There is no per-project config file to create, refresh, or keep comments in — the `aif` skill
scaffolds directories, not config.

## Workflow keys (lee-to → Hermes)

lee-to splits workflow behavior between `config.yaml`, `aif-handoff` env vars, and its coordinator
defaults. In Hermes these are `kanban.*` config keys plus per-board/per-task overrides:

| lee-to surface | Hermes equivalent | Default | Notes |
|----------------|-------------------|---------|-------|
| `AGENT_MAX_REVIEW_ITERATIONS` (aif-handoff env) | `kanban.max_review_iterations`; per-task `max_review_iterations` column | `3` | Rework-cycle cap before `manual_review_required`. The Hermes counter covers rework cycles of both gates (verify + review) |
| `AGENT_AUTO_REVIEW_STRATEGY` (aif-handoff env) | `kanban.auto_review_strategy` | `full_re_review` | `full_re_review` \| `closure_first` (closure_first only re-checks previous findings; new blockers after rework escalate to manual) |
| coordinator `runPlanImprove` | `kanban.run_plan_improve` | `false` | Inserts the `improve` stage (aif-improve) after planning |
| coordinator `runPostVerify` | `kanban.run_post_verify` | `true` | Inserts the `verify` stage (aif-verify) before review |
| `useSubagents` toggle | `kanban.use_subagents`; per-board `board.json` `use_subagents`; per-task `use_subagents` column (CLI `--delegation subagents\|skills`) | `true` (quality) | Resolution precedence: task → board → config. `true` = delegate to the `~/.claude/agents/` subagents; `false` = execute skill steps inline |
| `autoMode` (lee-to default **off**) | `auto_mode` per-task column (default **auto**); `--human-gates` at create time turns it off | auto | The Hermes department is autonomous by law (review PASS = acceptance); `--human-gates` restores lee-to's pausing at `plan_ready` and `done` |
| `HANDOFF_SKIP_REVIEW` | n/a in Hermes | — | review gates are pipeline stages, never silently skipped |
| poll scheduler (node-cron) | n/a — the gateway dispatcher (60s tick) already does this | — | duplicate machinery, consciously skipped |
| runtime adapters (claude/codex) | n/a — Hermes model routing (`model.default`, per-profile `model_override`) | — | |

## Per-board `board.json`

Each board can pin department behavior:

```json
{
  "orchestrator_profile": "aif_planner",
  "default_assignee": "aif_planner",
  "use_subagents": true
}
```

- `orchestrator_profile` — which profile orchestrates unassigned/triage work on this board
- `default_assignee` — assignee for cards created without one
- `use_subagents` — pins the board's delegation mode (overrides `kanban.use_subagents`,
  overridden by a per-task value)

## Paths — fixed `.hermes-dev/` layout

lee-to's entire `paths.*` section is replaced by one fixed convention (see
[Config Reference](config-reference.md#paths--fixed-mapping) for the key-by-key mapping):

```
~/Work/apps/<slug>/                # one app = one folder
├── DESCRIPTION.md                 # project specification (aif)
├── ARCHITECTURE.md                # architecture decisions (aif-architecture)
├── AGENTS.md                      # project-local agent notes (aif)
├── README.md                      # docs landing page (aif-docs)
├── docs/                          # detailed docs pages (aif-docs)
└── .hermes-dev/                   # dev-factory working directory
    ├── RULES.md                   # top-level axioms (aif-rules)
    ├── rules/                     # base.md + <area>.md (aif-rules)
    ├── plans/                     # plans <slug>.md + ROADMAP.md (aif-plan / aif-roadmap)
    ├── specs/                     # specs (aif-specify)
    ├── contracts/  gates/         # handoff/gate artifacts (pipeline roles)
    ├── research/RESEARCH.md       # persisted exploration (aif-explore)
    ├── fixes/FIX_PLAN.md          # fix plans (aif-fix)
    ├── patches/                   # self-improvement patches (aif-fix)
    ├── evolution/                 # evolution logs + patch-cursor.json (aif-evolve)
    ├── loop/                      # reflex loop state (aif-loop)
    │   ├── current.json
    │   └── <task-alias>/{run.json,history.jsonl,artifact.md}
    ├── skill-context/             # project-specific rules for built-in skills (aif-evolve)
    │   └── <skill-name>/SKILL.md
    ├── reference/                 # knowledge references + INDEX.md (aif-reference)
    ├── qa/                        # QA artifacts (aif-qa / aif-qa-check)
    │   ├── agent-context.md  agent-history.md
    │   └── <branch-slug>/{change-summary.md,test-plan.md,test-cases.md,qa-check.md}
    ├── SECURITY.md                # ignored security items (aif-security-checklist ignore)
    └── archive/                   # completed plans + roadmap snapshots (aif-archive)
        ├── plans/
        └── roadmap/
```

Skills also live at fixed locations:

- built-in skills: `~/.hermes/skills/<name>/` (global, verified via `hermes skills list`)
- subagents: `~/.claude/agents/*.md` (global — see [Subagents](subagents.md))

## Dropped lee-to config surfaces

| lee-to | Status in Hermes | Reason |
|--------|------------------|--------|
| `.ai-factory/config.yaml` (whole file) | n/a | no per-project user preferences file; workflow keys moved to `kanban.*`, paths are fixed |
| `.ai-factory.json` (agents[], installedSkills, managed hashes) | n/a | multi-runtime installer state is pointless with one global skills dir; the parity matrix tracks the port instead |
| `language.*` (ui/artifacts/technical_terms) | n/a | skills and skill-context are written in English (agent-consumed); user-facing replies follow the conversation language via Hermes profiles, artifacts follow the task/brief language when it matters |
| `git.*` (enabled/base_branch/create_branches/branch_prefix/skip_push_after_commit) | n/a as config | conventions instead: base branch auto-detected from the repo; branch/worktree creation is decided by the plan; push/merge without human approval is forbidden by department policy |
| `workflow.plan_id_format` (sequential numbering) | n/a | slug naming is canonical; numbered plans are a manual per-project choice |
| `workflow.verify_mode` | n/a as config | strictness is per-invocation (`--strict`) or per-gate policy |
| `workflow.auto_create_dirs`, `analyze_updates_architecture`, `architecture_updates_roadmap` | n/a | reserved keys with no reader even in lee-to; directories are scaffolded by `aif` |
| `rules.<area>` registration in config | replaced by name-based discovery | `.hermes-dev/rules/<area>.md` is discovered by filename; no registration step |
| MCP server templates per agent (`.mcp.json`, `.cursor/mcp.json`, …) | Hermes MCP configuration | MCP servers are configured once at the Hermes gateway level, not per project per runtime |
| extension registry (`extensions[]`) | n/a | see [Extensions](extensions.md) — the machinery is not wired; skills are added directly |

## Best Practices (retained from lee-to)

### Artifact Ownership and Context Gates
- Keep context artifact ownership skill-scoped (roadmap by `aif-roadmap`, rules by `aif-rules`,
  architecture by `aif-architecture`, research by `aif-explore`).
- Treat `aif-rules-check`, `aif-commit`, `aif-review`, and `aif-verify` as read-only consumers of
  context artifacts by default.
- Use `WARN` for non-blocking gate findings (missing optional files, ambiguous mapping) and
  `ERROR` for blocking violations.
- Quality gates emit the machine-readable `gate_result` with lowercase `pass` / `warn` / `fail`;
  see [Quality Gates](quality-gates.md).

### Logging
All implementations include verbose, configurable logging:
- Use log levels (DEBUG, INFO, WARN, ERROR)
- Control via `LOG_LEVEL` environment variable
- Implement rotation for file-based logs

### Commits
- Commit checkpoints every 3-5 tasks for large features
- Follow conventional commits format
- Meaningful messages, not just "update code"

### Testing
- Always decided before creating the plan (plan `Settings`)
- If "no tests" — no test tasks created
- Never sneaks in test code

## See Also

- [Config Reference](config-reference.md) — key-by-key mapping tables
- [Getting Started](getting-started.md) — workspace convention, first project
- [Development Workflow](workflow.md) — how the workflow keys drive the stage machine
- [Reflex Loop](loop.md) — `.hermes-dev/loop/` storage layout
- [Extensions](extensions.md) — third-party additions in Hermes
- [Security](security.md) — reviewing external skills before use
