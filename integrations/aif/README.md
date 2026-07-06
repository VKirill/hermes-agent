# AIF — AI Factory for Hermes

A full port of **[lee-to's AI Factory](https://github.com/lee-to/ai-factory)** (2.x) — including
the `aif-handoff` orchestration policies — into the **Hermes native kanban**. One kanban card
becomes a complete software-delivery pipeline: specification, planning, implementation,
verification, and independent review, each stage executed by a dedicated role profile, with
machine-readable quality gates and a convergence-aware review loop.

All credit for the methodology, the skill/subagent content, and the original stage-machine and
review-gate design goes to [lee-to](https://github.com/lee-to). This integration adapts that work
to Hermes: the orchestration that upstream implements as a standalone handoff service lives here
in the Hermes kanban core, and the skills/subagents are adapted to Hermes conventions (profiles,
`hermes kanban` CLI, `.hermes-dev/` artifacts, `gate_result` tool contract).

## What's in the box

| Component | Where | What |
|---|---|---|
| Workflow core | committed on this branch (see [CHANGES.md](CHANGES.md)) | AIF stage machine, convergence review gate, `gate_result` contract, per-board orchestration, human gate CLI, dashboard UI |
| 31 skills | [`skills/`](skills/) | 30 `aif-*` workflow/utility skills (spec, plan, implement, verify, review, security, loop, evolve, …) + `dev-handoff` (routes dev requests from conversational topics into the factory) |
| 19 subagents | [`agents/`](agents/) | Claude Code subagent definitions: plan/implement coordinators and workers, review/security/rules/best-practices sidecars, commit-preparer, docs-auditor, and the 9 Reflex Loop roles |
| 5 role profiles | [`profiles/`](profiles/) | `SOUL.md` for `aif_specifier`, `aif_planner`, `aif_implementer`, `aif_verifier`, `aif_reviewer` |
| Installer | [`install.sh`](install.sh) | Idempotent installer for all of the above |

## Architecture

One card walks the stage machine; the stage lives in the card's `current_step_key`:

```
spec → planning → (improve) → plan_ready* → implementing → (verify) → review → done* → verified
```

| Stage | Role profile | Skill | Notes |
|---|---|---|---|
| `spec` | `aif_specifier` | `aif-specify` | Goal/scope/acceptance/contracts into `.hermes-dev/specs/` |
| `planning` | `aif_planner` | `aif-plan` | Plan file with checklist + dependency order |
| `improve` | `aif_planner` | `aif-improve` | Optional plan-polish stage (`kanban.run_plan_improve`) |
| `plan_ready`* | — (human gate) | — | Approve the plan: `gate-action start_implementation \| request_replanning` |
| `implementing` | `aif_implementer` | `aif-implement` | One task at a time, evidence handoff |
| `verify` | `aif_verifier` | `aif-verify` | Optional acceptance gate (`kanban.run_post_verify`); emits `gate_result` |
| `review` | `aif_reviewer` | `aif-review` | Independent review gate; emits `gate_result`; convergence loop below |
| `done`* | — (human gate) | — | `approve` (→ `verified`) or `request-changes` (→ rework) |
| `verified` | — | — | Terminal: card status `done` + step `verified` |

- **Each stage advance rewrites the card's assignee to the stage's role profile**, so the stock
  Hermes dispatcher routes stages with zero routing changes.
- For a stage worker, `kanban_complete` means "my **stage** is done", not the card — the kernel
  advances the card and re-readies it for the next role.
- **Human gates** (`*` = `plan_ready`, `done`) surface as `blocked`/`needs_input`. In **auto mode
  (the default)** they are skipped; create the card with `--human-gates` to enable them. A generic
  `unblock` on a gate card is refused by design — gates are answered only through the explicit gate
  actions.
- Stage transitions are exempt from the dispatcher's `recent_success`/`active_pr` respawn guards
  (a completed run is exactly how a stage hands off).

## The convergence review gate

Gate stages (verify/review/security) must return one machine-readable verdict — the
**`gate_result` contract** — attached to `kanban_complete` (pass/warn) or `kanban_block` (fail):

```json
{
  "schema_version": 1,
  "gate": "spec|verify|review|security|rules|qa|qa-check",
  "status": "pass|warn|fail",
  "blocking": false,
  "blockers": [{ "summary": "stable one-line finding id", "details": "..." }],
  "affected_files": ["..."],
  "suggested_next": { }
}
```

`blockers[].summary` strings are the **stable finding ids**: the convergence gate compares them
across review rounds. The decision tree on a review-stage verdict:

- **pass / warn** → stage advances (review → done gate → verified).
- **fail** → **rework**: the card returns to `implementing` with the findings carried in the
  card's review state, and the implementer sees them in its stage banner. Iteration count
  increments.
- **fail, and the iteration cap is hit** (`kanban.max_review_iterations`, default 3) →
  **`manual_review_required`**: the card stops at the `done` human gate for a person to decide.
- **fail with new blockers after the previous ones were closed** (under the `closure_first`
  strategy, `kanban.auto_review_strategy`) → **`manual_review_required`** — the loop is not
  converging, a person decides. The alternative strategy `full_re_review` re-litigates the full
  finding set each round.
- **malformed verdict** (missing/unparseable `gate_result`) → **`manual_review_required`**.
  The gate never guesses: **an unparseable review never reads as PASS**. On the tool boundary this
  is fail-closed too — `kanban_complete` on a verify/review stage *requires* a validated
  `gate_result`, and a blocking verdict passed to `kanban_complete` is rejected and routed to
  `kanban_block`.

## Usage

Create a workflow card:

```sh
hermes kanban create "Add CSV export to the report page" --workflow aif \
    [--project <slug>]                  # bind to a project (worktree workspace)
    [--human-gates]                     # enable plan_ready/done human gates
    [--delegation subagents|skills]     # per-card delegation mode
    [--model <model>]                   # per-task model override (e.g. pin review models)
```

Human actions on gate cards (CLI or the dashboard gate buttons):

```sh
hermes kanban approve <task_id>                     # done gate → verified (terminal)
hermes kanban request-changes <task_id> --reason "…" # done gate → back to implementing
hermes kanban gate-action <task_id> start_implementation|request_replanning  # plan_ready gate
```

When a worker blocks with a question, answer **and resume in one call** (a comment alone never
resumes a blocked task):

```sh
hermes kanban comment <task_id> "<answer>" --unblock
```

Conversational topics route dev requests into the factory with the `dev-handoff` skill: it files a
triage card on the `departments` board (the default board name, pinned to the `aif_planner`
orchestrator by the installer) and subscribes the originating topic so progress and completion
land back in the conversation.

### Delegation modes

Each stage skill names coordinators/sidecars it can delegate to. Resolution order:
per-card `--delegation` → board `board.json` → `kanban.use_subagents` config → **on**.

- **subagents** — the stage worker spawns the packaged Claude Code subagents
  (`plan-coordinator`/`plan-polisher` for planning, `implement-coordinator`/`implement-worker`
  plus the review/security/rules/best-practices sidecars for implementation, the `loop-*` roles
  for `aif-loop`).
- **skills** — everything runs inline in the stage worker's own session.

### Workspace convention

One app = one folder under the apps root — by default `~/Work/apps/<slug>/` (the path the skills
document; adjust to taste, it is plain convention, not code) — with a standardized
`.hermes-dev/{plans,specs,contracts,gates,rules,skill-context}` artifact tree. For a new app the
planner bootstraps the Hermes project and the folder.

## Install

Requirements:

- A Hermes checkout with this branch's core commits merged (see [CHANGES.md](CHANGES.md)) —
  the stage machine, gate contract, and CLI verbs live in Hermes core, not in this directory.
- `python3` (with PyYAML for the config merge — Hermes itself depends on it).
- Claude Code (for the subagent delegation mode; skills mode works without it).

```sh
./install.sh
```

The installer is idempotent. It:

1. copies the 31 skills into `~/.hermes/skills/`,
2. copies the 19 subagents into `~/.claude/agents/`,
3. creates the 5 role profiles if missing (`hermes profile create`) and installs each `SOUL.md`,
4. merges `skills.external_dirs: ["~/.hermes/skills"]` into each role profile's `config.yaml`
   (merge, not overwrite — `approvals.mode` and all other keys are preserved),
5. pins the `departments` board to `orchestrator_profile=aif_planner` /
   `default_assignee=aif_planner` via `hermes_cli.kanban_db.write_board_metadata` (printed as a
   manual step if `hermes_cli` is not importable),

and prints the post-install checklist: the optional `kanban.max_review_iterations`,
`kanban.auto_review_strategy`, `kanban.use_subagents`, `kanban.run_plan_improve`,
`kanban.run_post_verify` config keys, and a gateway restart.

`HERMES_HOME` (default `~/.hermes`) and `CLAUDE_AGENTS_DIR` (default `~/.claude/agents`) are
respected.

## Directory layout

```
integrations/aif/
├── README.md          this file
├── CHANGES.md         the core commits on this branch, one line each
├── install.sh         idempotent installer
├── skills/            30 aif-* skills + dev-handoff (SKILL.md, references/, templates/, tests/)
├── agents/            19 Claude Code subagent definitions
└── profiles/          5 role profiles (SOUL.md each)
```

`skills/aif-methodology` is the department's single shared reference ("the AGENTS.md of the
department"): the pipeline, the gate contract, the `.hermes-dev` convention, the no-stall laws,
and a 12-document reference library (`references/docs/`) ported from upstream `docs/`.

## License and attribution

The skills and subagents in this directory are **adapted ports of lee-to's
[ai-factory](https://github.com/lee-to/ai-factory)**, which is published under the **MIT
license** (per its `package.json` and README; the upstream repository ships no separate LICENSE
file — upstream ai-factory license terms apply to the ported skill/subagent content). The
adaptations and the Hermes-side integration code follow the license of this repository (MIT).

Please credit lee-to when redistributing the skill/subagent content.
