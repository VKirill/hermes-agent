Next: [Development Workflow →](workflow.md) · [AIF methodology](../../SKILL.md)

> Ported from lee-to AI Factory `docs/getting-started.md`, retargeted to the Hermes AIF department.

# Getting Started

## What is the AIF department?

The Hermes AIF department is a port of lee-to's **AI Factory** — a stack-agnostic, spec-driven
development system — running as a role pipeline on the Hermes `departments` kanban board:

1. **Analyzes your project** — understands the codebase structure and conventions (`aif`, `aif-explore`)
2. **Provides spec-driven workflow** — structured feature development with plans, tasks, and commits
   (`aif-plan` → `aif-implement` → `aif-verify` → `aif-review`)
3. **Learns from its own bugs** — every fix leaves a patch; `aif-evolve` distills patches into
   project-specific skill rules
4. **Gates quality mechanically** — verify/review/security/rules gates emit a machine-readable
   `gate_result` consumed by the kanban workflow core

All 28 `aif-*` skills live in `~/.hermes/skills/` (verify with `hermes skills list`). There is no
`ai-factory init` / npm installer step in Hermes — the skills are installed once, globally, and every
app project just follows the standardized workspace convention.

## Workspace convention

One app = one folder:

```
~/Work/apps/<slug>/
├── DESCRIPTION.md          # project specification (root, written by the aif skill)
├── ARCHITECTURE.md         # architecture decisions (root, owned by aif-architecture)
├── AGENTS.md               # project-local agent notes (root)
├── README.md + docs/       # human documentation (owned by aif-docs)
└── .hermes-dev/            # dev-factory artifacts
    ├── plans/  specs/  contracts/  gates/  rules/  skill-context/
    ├── research/  fixes/  qa/  evolution/  loop/  patches/  archive/  reference/
    └── RULES.md
```

The `aif` skill bootstraps a **new** app: it creates the folder, scaffolds `.hermes-dev/`, inits git,
registers the Hermes project (`hermes project create "<App Name>" --slug <slug> --primary
~/Work/apps/<slug> --board departments`), and generates DESCRIPTION.md / AGENTS.md / base rules.

## Two ways in

### 1. From a conversation topic — `dev-handoff`

Dev work discussed in any Hermes topic is routed to the department via the `dev-handoff` skill:
it triages the request onto the `departments` board and subscribes the topic, so progress and the
final result flow back to where the conversation happened.

### 2. Directly — one workflow card

```bash
# Put ONE card through the whole spec→plan→implement→verify→review pipeline:
hermes kanban --board departments create "Add user authentication with OAuth" \
  --workflow aif --project <slug>

# Optional: start at a specific stage (default entry is planning; spec is the optional pre-stage)
hermes kanban create "..." --workflow aif --workflow-step spec --project <slug>

# Optional: keep lee-to's human gates (pause at plan_ready and done for approval)
hermes kanban create "..." --workflow aif --human-gates --project <slug>

# Optional: pin delegation mode for this card (subagents vs inline skills)
hermes kanban create "..." --workflow aif --delegation subagents|skills --project <slug>
```

The stage machine advances the card automatically: each stage is claimed by its role profile
(`aif_specifier`, `aif_planner`, `aif_implementer`, `aif_verifier`, `aif_reviewer`), gate failures
loop back through fix tasks, and the card only becomes terminal at `verified`.
See [Development Workflow](workflow.md#hermes-stage-machine) for the full stage machine.

## Your first project

```bash
# 1. New app? Create the workflow card with a project slug — aif-plan's bootstrap step
#    (or the aif skill interactively) creates ~/Work/apps/<slug>/ + .hermes-dev/ + the Hermes project.
hermes kanban --board departments create "Bootstrap <app>: <what it does>" --workflow aif --project <slug>

# 2. Existing app? Same command — the pipeline works inside the existing folder.

# 3. Interactive alternative (Claude Code session in the app folder):
#    load skill `aif`            — set up context (DESCRIPTION.md, AGENTS.md, rules)
#    load skill `aif-explore`    — optional discovery before planning
#    load skill `aif-plan`       — plan the work
#    load skill `aif-implement`  — execute the plan
```

If scope is unclear, start with `aif-explore` (optionally save results to
`.hermes-dev/research/RESEARCH.md`); if the task is clear but the answer must be strictly verified,
use `aif-grounded`; if the direction is already clear, go straight to `aif-plan`.

## Useful commands

```bash
# Skills
hermes skills list                       # verify all aif-* skills are visible

# Kanban workflow
hermes kanban --board departments show <id>       # card + stage + gate history
hermes kanban approve <id>                        # human gate: approve (plan_ready / done)
hermes kanban request-changes <id> "<reason>"     # human gate: send back to implementing
hermes kanban gate-action <id> <action>           # explicit gate action (start_implementation,
                                                  # request_replanning, approve_done, request_changes)

# Projects
hermes project create "<App>" --slug <slug> --primary ~/Work/apps/<slug> --board departments
```

## What replaced the lee-to installer

| lee-to | Hermes |
|--------|--------|
| `npm install -g ai-factory` + `ai-factory init` | n/a — skills are already in `~/.hermes/skills/` |
| per-agent skills dirs (`.claude/skills/`, `.cursor/skills/`, …) | one global skills dir; workers load skills by name |
| `ai-factory update` / `upgrade` | refresh the skill folders in `~/.hermes/skills/` (the port is maintained via the parity matrix) |
| `ai-factory init --mcp ...` | Hermes MCP configuration (gateway config), out of scope for this doc |
| skills.sh search/install | manual: add the skill folder to `~/.hermes/skills/`, security-review it first (see [Security](security.md)), verify via `hermes skills list` |
| `/aif-*` slash commands | load skill `aif-*` (kanban workers); slash still works in interactive Claude Code sessions |

## Next steps

- [Development Workflow](workflow.md) — the full flow from plan to commit, plus the Hermes stage machine
- [Reflex Loop](loop.md) — iterative generate → evaluate → critique → refine cycles
- [Core Skills](skills.md) — reference for all 28 `aif-*` skills
- [Configuration](configuration.md) — how lee-to's `config.yaml` maps onto Hermes config
