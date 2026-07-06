[← Configuration](configuration.md) · [AIF methodology](../../SKILL.md)

> Rewritten for Hermes: this is the key-by-key mapping from lee-to's `.ai-factory/config.yaml`
> (and `aif-handoff` env vars) to their Hermes equivalents. For the architecture of where config
> lives, see [Configuration](configuration.md).

# Config Reference

Use this page when you need to know:
- which Hermes `kanban.*` keys exist, their defaults, and the override chain,
- what happened to each lee-to `config.yaml` key,
- which per-board and per-task overrides are available.

## Hermes workflow keys

Set in the Hermes gateway config under `kanban.*`. Override precedence for keys that have it:
**per-task column → per-board `board.json` → `kanban.*` config → built-in default.**

| Key | Default | Overrides | Meaning |
|-----|---------|-----------|---------|
| `kanban.max_review_iterations` | `3` | per-task `max_review_iterations` | Convergence cap: rework cycles (verify + review combined) before the card escalates to `manual_review_required (max_iterations)` |
| `kanban.auto_review_strategy` | `full_re_review` | — | `full_re_review`: every re-review is a full review. `closure_first`: re-review checks closure of previous findings first; previously-resolved findings plus NEW blockers → `manual_review_required (new_blockers_after_rework)` |
| `kanban.run_plan_improve` | `false` | — | When true, the aif workflow inserts the `improve` stage (aif-improve pass on the fresh plan) between `planning` and `plan_ready` |
| `kanban.run_post_verify` | `true` | — | When true, the aif workflow inserts the `verify` stage (aif-verify gate) between `implementing` and `review` |
| `kanban.use_subagents` | `true` | board `use_subagents` → per-task `use_subagents` (CLI `--delegation subagents\|skills`) | Delegation mode: `true` = spawn the ported `~/.claude/agents/` subagents (coordinators, sidecars, loop-* roles) via the Agent tool; `false` = execute skill steps inline in the worker session |

## Per-task workflow fields

Set at create time (`hermes kanban create --workflow aif ...`) or stored as task columns:

| Field | Default | CLI | Meaning |
|-------|---------|-----|---------|
| `auto_mode` | auto (**on**) | `--human-gates` sets it off | On: human gates `plan_ready` and `done` are skipped, the card flows to `verified` on green gates. Off: the card pauses as `blocked`/`needs_input` at each human gate and waits for `hermes kanban approve` / `request-changes` / `gate-action`. Note: lee-to defaults autoMode **off**; the Hermes department is autonomous by law, so the default is inverted |
| `max_review_iterations` | NULL (→ `kanban.max_review_iterations`) | — | Per-card rework cap override |
| `use_subagents` | NULL (→ board → config) | `--delegation subagents\|skills` | Per-card delegation mode |
| entry stage | `planning` | `--workflow-step <stage>` | e.g. `spec` to run the optional specifier pre-stage first |

## Per-board `board.json`

| Field | Meaning |
|-------|---------|
| `orchestrator_profile` | Profile that orchestrates triage/unassigned work on this board (for the departments board: `aif_planner` — the dev lead) |
| `default_assignee` | Assignee for cards created without one |
| `use_subagents` | Board-level pin of the delegation mode (between per-task and `kanban.use_subagents`) |

## lee-to `config.yaml` → Hermes, key by key

### `language`

| lee-to key | lee-to default | Hermes |
|------------|----------------|--------|
| `language.ui` | `en` | n/a — user-facing replies follow the conversation language via Hermes profiles; worker/gate output stays English |
| `language.artifacts` | `en` | n/a — dev artifacts and skill-context are written in English (agent-consumed); human-facing docs follow the task/brief language when the task says so |
| `language.technical_terms` | `keep` | n/a — commands, paths, identifiers, config keys, and raw errors are always kept verbatim (hard convention) |

### `paths` — fixed mapping

Every `paths.*` key becomes a fixed location (no relocation possible):

| lee-to key | lee-to default | Hermes fixed path |
|------------|----------------|-------------------|
| `paths.description` | `.ai-factory/DESCRIPTION.md` | `DESCRIPTION.md` (project root) |
| `paths.architecture` | `.ai-factory/ARCHITECTURE.md` | `ARCHITECTURE.md` (project root) |
| — (`AGENTS.md`) | project root | `AGENTS.md` (project root) — unchanged |
| `paths.docs` | `docs/` | `docs/` (project root; follow an existing docs dir convention if the project has one) |
| `paths.roadmap` | `.ai-factory/ROADMAP.md` | `.hermes-dev/plans/ROADMAP.md` |
| `paths.research` | `.ai-factory/RESEARCH.md` | `.hermes-dev/research/RESEARCH.md` |
| `paths.rules_file` | `.ai-factory/RULES.md` | `.hermes-dev/RULES.md` |
| `paths.rules` | `.ai-factory/rules/` | `.hermes-dev/rules/` (base.md + `<area>.md`, discovered by name) |
| `paths.plan` (fast plan) | `.ai-factory/PLAN.md` | n/a — all plans go to `.hermes-dev/plans/<slug>.md` |
| `paths.plans` | `.ai-factory/plans/` | `.hermes-dev/plans/` |
| `paths.fix_plan` | `.ai-factory/FIX_PLAN.md` | `.hermes-dev/fixes/FIX_PLAN.md` |
| `paths.security` | `.ai-factory/SECURITY.md` | `.hermes-dev/SECURITY.md` |
| `paths.references` | `.ai-factory/references/` | `.hermes-dev/reference/` (singular) + `INDEX.md` |
| `paths.patches` | `.ai-factory/patches/` | `.hermes-dev/patches/` |
| `paths.evolutions` (evolve logs + cursor) | `.ai-factory/evolutions/` | `.hermes-dev/evolution/` |
| `paths.evolution` (reflex loop state) | `.ai-factory/evolution/` | `.hermes-dev/loop/` |
| `paths.specs` | `.ai-factory/specs/` | `.hermes-dev/specs/` |
| `paths.qa` | `.ai-factory/qa/` | `.hermes-dev/qa/` (branch slug appended: `.hermes-dev/qa/<branch-slug>/`) |
| `paths.archive` | `.ai-factory/archive/` | `.hermes-dev/archive/` (`plans/`, `roadmap/`) |
| — (skill-context, fixed in lee-to too) | `.ai-factory/skill-context/` | `.hermes-dev/skill-context/` |

Note the deliberate disambiguation: lee-to's confusing `evolutions/` (evolve logs) vs `evolution/`
(loop state) pair became `evolution/` vs `loop/` in Hermes.

### `workflow`

| lee-to key | lee-to default | Hermes |
|------------|----------------|--------|
| `workflow.auto_create_dirs` | `true` | n/a — the `aif` skill scaffolds `.hermes-dev/`; skills `mkdir -p` their own artifact dirs |
| `workflow.plan_id_format` | `slug` | n/a — slug naming is canonical; `sequential`/`timestamp`/`uuid` not supported (numbered plans are a manual per-project choice; `aif-archive` preserves any filename) |
| `workflow.analyze_updates_architecture` | `true` | n/a — reserved key with no reader in lee-to either |
| `workflow.architecture_updates_roadmap` | `true` | n/a — reserved key with no reader in lee-to either |
| `workflow.verify_mode` | `normal` | n/a as config — strictness is per-invocation (`aif-verify --strict`) and per-stage gate policy |

### `git`

| lee-to key | lee-to default | Hermes |
|------------|----------------|--------|
| `git.enabled` | `true` | n/a — presence of a `.git` repo is detected; no-git projects fall back to working-tree diffing (aif-qa asks for / reads manual change context) |
| `git.base_branch` | `main` | n/a — auto-detected from the repo (`origin/HEAD` → `main`/`master`); skills must not hardcode `main` |
| `git.create_branches` | `true` | n/a — branch/worktree creation is a plan-level decision; per-task git isolation (worktree per implement stage) is a planned core feature, see the parity matrix |
| `git.branch_prefix` | `feature/` | n/a — convention stays `feature/` when a branch is created |
| `git.skip_push_after_commit` | `false` | n/a — stronger rule: `aif-commit` never pushes/merges without human approval (department policy) |

### `rules`

| lee-to key | lee-to default | Hermes |
|------------|----------------|--------|
| `rules.base` | `.ai-factory/rules/base.md` | `.hermes-dev/rules/base.md` (fixed) |
| `rules.<area>` (registered in config) | none | `.hermes-dev/rules/<area>.md` — discovered by filename, no registration. Hierarchy unchanged: `rules/<area>.md` > `rules/base.md` > `RULES.md` |

### `aif-handoff` env vars

| lee-to env | Hermes |
|------------|--------|
| `AGENT_MAX_REVIEW_ITERATIONS` | `kanban.max_review_iterations` |
| `AGENT_AUTO_REVIEW_STRATEGY` | `kanban.auto_review_strategy` |
| `HANDOFF_MODE` / `HANDOFF_TASK_ID` | n/a — workers are native kanban workers; the task id is the session's task |
| `HANDOFF_SKIP_REVIEW` | n/a — review gates are pipeline stages, never bypassed by env var |
| `HANDOFF_BRANCH_PREPARED` | n/a — no sequential-numbering interaction to disable |
| `GITHUB_TOKEN` (extension refresh rate limits) | n/a — no extension refresh machinery; `gh` CLI auth covers GitHub operations |

## Skill read/write matrix (Hermes)

With no config file, the matrix degenerates to artifact ownership — see the ownership tables in
[Development Workflow](workflow.md#artifact-ownership-and-context-gates) and
[Plan Files](plan-files.md#artifact-ownership-quick-map). Highlights:

- **Writers of shared context:** `aif` (DESCRIPTION.md, AGENTS.md), `aif-architecture`
  (ARCHITECTURE.md), `aif-roadmap` (ROADMAP.md), `aif-rules` (RULES.md, rules/),
  `aif-explore` (RESEARCH.md), `aif-evolve` (skill-context, evolution logs).
- **Read-only gates:** `aif-verify`, `aif-review`, `aif-rules-check`, `aif-commit`,
  `aif-security-checklist` (except its `ignore` writer flow → `.hermes-dev/SECURITY.md`).
- **Repo-driven, context-free:** `aif-best-practices`, `aif-build-automation`, `aif-ci`,
  `aif-dockerize`, `aif-grounded`, `aif-skill-generator` (lee-to's "config-agnostic" set — in
  Hermes every skill is config-agnostic by construction; these are additionally
  shared-context-light).

## See Also

- [Configuration](configuration.md) — high-level config architecture and the fixed layout
- [Core Skills](skills.md) — full skill reference
- [Development Workflow](workflow.md) — where the workflow keys drive the stage machine
