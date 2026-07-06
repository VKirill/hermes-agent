---
name: aif-methodology
description: >-
  The single source of truth for how the Hermes AI Factory department works — the
  spec→plan→implement→verify→review pipeline, the gate_result contract, the per-app
  .hermes-dev artifact convention, and the no-stall department laws. Reference doc (the
  AGENTS.md of this department). Load it when an aif_* worker needs the whole-department
  picture; per-role step-by-step procedure lives in each role's own aif-* skill.
tags:
  - aif
  - methodology
  - dev-factory
  - reference
---

# AIF methodology — how the department works

Single shared reference for the AI Factory department (port of lee-to's AI Factory, adapted to Hermes). Do **not** duplicate this into profile SOULs — point to it.

## The pipeline
Work flows through five roles on the Hermes `departments` kanban board, orchestrated by `aif_planner`:

```
spec (aif_specifier) → plan (aif_planner) → implement (aif_implementer) → verify (aif_verifier) → review (aif_reviewer)
```

- Each stage reads the kanban task + parent handoffs, does **only** its scoped job, and hands off structured evidence to the next stage. Never redo an upstream stage; never do a downstream stage's job.
- Each role's step-by-step "how" lives in its own skill: `aif-specify`, `aif-plan`, `aif-implement`, `aif-verify`, `aif-review` (+ `aif-security-checklist`). Load your Core skill and follow it.

## Two ways work flows

1. **Workflow card (preferred, port of aif-handoff):** ONE card created with
   `hermes kanban create --workflow aif` walks the stage machine
   `spec → planning → (improve) → plan_ready* → implementing → (verify) → review → done* → verified`
   (`*` = human gates, skipped in auto mode — the default). Each stage transition rewrites the
   assignee to the stage's role profile. **`kanban_complete` = your STAGE is done**, not the card —
   the kernel advances it. Terminal = `verified`.
   - Gate stages (verify/review) MUST attach `gate_result` to `kanban_complete` (pass/warn) or
     `kanban_block` (fail). A FAIL runs the **convergence gate**: findings (stable ids from
     `blockers[].summary`) are compared across rounds; the card returns to `implementing` with the
     findings carried (rework), until `kanban.max_review_iterations` (default 3) trips →
     `manual_review_required` at the done human gate. New blockers after old ones closed
     (`closure_first` strategy) and malformed verdicts also stop at the human — **an unparseable
     review NEVER reads as PASS**.
   - Human gate actions: `hermes kanban approve <id>` (done→verified), `request-changes <id>
     --reason`, `gate-action <id> start_implementation|request_replanning` — or the dashboard
     buttons. A generic `unblock` on a gate is refused by design.
   - Delegation mode per card: `use_subagents` (task → board.json → `kanban.use_subagents` → on).
     Subagents mode = spawn the coordinators/sidecars your skill names; skills mode = inline.
2. **Multi-card pipeline (legacy/manual):** separate linked tasks per stage, dependencies via
   `link`. The no-stall laws below still apply; the review→fix loop is closed by the reviewer
   spawning a fix task (idempotency-key `fix:<id>`).

## Workspace convention
One app = one folder `~/Work/apps/<slug>/` with standardized `.hermes-dev/{plans,specs,contracts,gates,rules,skill-context}`. New app → `aif_planner` bootstraps the project + folder (see `aif-plan` Step 3.5). Read/write your artifacts there.

## Gate contract
Gates (`aif-verify`, `aif-review`, `aif-security-checklist`) emit one machine-readable JSON block, passed via `kanban_complete` (pass/warn) or `kanban_block` (fail):

```
{ "schema_version": 1, "gate": "spec|verify|review|security|rules|qa|qa-check", "status": "pass|warn|fail",
  "blocking": bool, "blockers": [...], "affected_files": [...], "suggested_next": {...} }
```

## No-stall department laws
- **Complete on evidence.** Green checks → `kanban_complete`, not "await human approval". Human approval only for irreversible/prod actions (deploy/publish/migrate/spend/force-push/merge).
- **Verifier PASS = acceptance.** A verify+review PASS is the acceptance authority.
- **Close the review→fix loop.** A fail verdict MUST spawn a fix task for `aif_implementer` (idempotency-key) and gate re-review on it — never leave a blocker without a fixer.
- **Dev lead.** `aif_planner` owns decomposition (full role pipeline), gate synthesis, and the done/rework decision.
- **Block only for real reasons.** Real failure, missing context/access, or an irreversible prod action — not "no human approval yet".

## Handoff in / out
Conversational topics route dev work here via the `dev-handoff` skill (triage on `departments` + subscribe the topic). Progress returns to the originating topic via the task subscription.

## Docs

Methodology reference library (port of lee-to AI Factory `docs/`, adapted to Hermes) in `references/docs/`:

- `getting-started.md` — onboarding: workspace convention, dev-handoff vs `hermes kanban create --workflow aif`, first project, what replaced the lee-to installer.
- `workflow.md` — the full development workflow (explore→plan→improve→implement→verify→commit→evolve), artifact ownership, context gates, plus the Hermes stage machine (spec→…→verified, human gates, convergence).
- `loop.md` — Reflex Loop protocol: phases, `.hermes-dev/loop/` persistence model, rule schema, stop conditions, iteration output contracts.
- `evolve.md` — the fix→patch→evolve learning loop, skill-context format and priority, stale-rule cleanup, worker-mode defaults.
- `quality-gates.md` — the machine-readable `gate_result` contract (schema, examples, stable finding ids) and what the workflow core does with each verdict.
- `plan-files.md` — plan/fix-plan/patch artifacts, archive lifecycle, artifact frontmatter convention, Original Request / Research Context rules, skill acquisition strategy.
- `security.md` — mandatory two-level review (pattern checklist + LLM semantic review) for external skills before they enter `~/.hermes/skills/`.
- `configuration.md` — where configuration lives in Hermes (kanban.* keys, board.json, per-task fields, fixed `.hermes-dev/` layout) and which lee-to config surfaces were dropped.
- `config-reference.md` — key-by-key mapping: lee-to `config.yaml` / aif-handoff env vars → Hermes equivalents with defaults and override chains.
- `skills.md` — reference for all workflow and utility skills (adapted per-skill contracts, paths, gate emissions) + the Hermes-only skills.
- `subagents.md` — the 19 subagents in `~/.claude/agents/` (global), coordinators/sidecars/loop roles, delegation gated by `use_subagents`, top-level session constraints.
- `extensions.md` — concept port: how each lee-to extension capability is achieved in Hermes (the extension.json machinery is not wired; skills go directly to `~/.hermes/skills/`).

## Technical blockers — fix them yourself (no-stall)
- Missing a tool/package (npm package, pip, brew formula, CLI)? INSTALL IT YOURSELF in user space (npm i/npx, pip install --user, brew install) and continue — this is NOT a reason to block and does NOT require approval.
- Block on capability only when you need: an admin password, a paid license/subscription, physical access, or a system reboot.
- Even then — do NOT leave the blocker to the human if another agent can clear it: create a fix task for your infrastructure/ops profile (`hermes kanban --board departments create "Install <tool>" --assignee <infra_profile> --idempotency-key install:<tool>`), run `link <fix_id> <your_task>`, and block with `kind=dependency` — after the install your task WAKES UP BY ITSELF, without a human.
- Leave for the human (owner gate) only: money, live campaigns/ad accounts, production deploys to a client domain, outbound sending, and secrets.
