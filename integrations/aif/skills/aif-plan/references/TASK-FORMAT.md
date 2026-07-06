# aif-plan Task and Plan Format

Ported from lee-to AI Factory `/aif-plan`, adapted to Hermes: plans live under
`.hermes-dev/plans/` in the app's own folder, there is no `.ai-factory/config.yaml`
(naming conventions are project rules), and downstream tasks are created with the
native `hermes kanban` CLI instead of lee-to's `TaskCreate`.

## Plan File Naming

Default (Hermes): `.hermes-dev/plans/<slug>.md` — slug derived from the task
description: lowercase, hyphenated, ≤50 chars. For a new app the plan lives in the
app's folder: `~/Work/apps/<slug>/.hermes-dev/plans/<slug>.md`.

Optional sequential prefix — active only when the project declares it in
`.hermes-dev/RULES.md` (e.g. "Plan files use a 4-digit sequential prefix:
`NNNN_<slug>.md`"):

| Convention   | Filename shape                            | Notes                                                                                                                                                                                                                                                          |
|--------------|-------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| default      | `.hermes-dev/plans/<slug>.md`             | Slug from the task description (or the app slug for a brand-new app).                                                                                                                                                                                          |
| `sequential` | `.hermes-dev/plans/<NNNN>_<slug>.md` (4-digit, zero-padded) | `NNNN = max(existing 4-digit prefixes in .hermes-dev/plans/) + 1`; an empty dir starts at `0001`; hard cap `9999` — on cap, block the kanban task instead of writing `10000_` (consumer globs in aif-implement/aif-verify are 4-digit). Only `.hermes-dev/plans/` counts: plans archived under `.hermes-dev/archive/plans/` never influence numbering. Numbers derive from existing files — deleting the highest-numbered plan frees that number for reuse. |

lee-to's `timestamp` / `uuid` reserved formats and the `workflow.plan_id_format`
config key are dropped: Hermes has no config file for this — the convention is a
project rule. Fix plans are a separate single artifact owned by `aif-fix`
(`.hermes-dev/fixes/`) and ignore the sequential convention.

## Plan File Template

```markdown
# Implementation Plan: [Feature Name]

Branch: [current branch or "none"]
Created: [date]

## Original Request
<!-- Required when an explicit planning request was supplied (kanban task body or
     user message). Omit only when the plan was created solely from
     .hermes-dev/research/RESEARCH.md without an explicit request. Preserve the
     request verbatim after trimming outer whitespace; do not translate,
     summarize, normalize, or rewrite it. -->
[exact planning request]

## Settings
- Testing: yes/no
- Logging: verbose/standard/minimal
- Docs: yes/no  # yes => mandatory docs checkpoint in aif-implement, no/unset => WARN [docs] only

## Roadmap Linkage (optional)
<!-- Only when .hermes-dev/plans/ROADMAP.md exists -->
Milestone: "[milestone name from ROADMAP.md]"  # or "none"
Rationale: [1 short sentence]

## Research Context (optional)
<!-- Only when .hermes-dev/research/RESEARCH.md content influenced this plan;
     copy the relevant Active Summary here -->
Source: .hermes-dev/research/RESEARCH.md (Active Summary, Updated: YYYY-MM-DD HH:MM, SHA256: <active-summary-sha256>)
<!-- The copied context is the committed requirements snapshot; downstream skills
     use the live research file only to warn about revision drift. -->

Goal:
Constraints:
Decisions:
Open questions:

## Commit Plan
<!-- For plans with 5+ tasks, define commit checkpoints -->
- **Commit 1** (after tasks 1-3): "feat: add base models and types"
- **Commit 2** (after tasks 4-6): "feat: implement core service logic"

## Tasks

### Phase 1: Setup
- [ ] Task 1: [description]
- [ ] Task 2: [description]

### Phase 2: Core Implementation
- [ ] Task 3: [description] (depends on 1, 2)
- [ ] Task 4: [description]
<!-- Commit checkpoint: tasks 1-4 -->

### Phase 3: Integration
- [ ] Task 5: [description] (depends on 3, 4)
<!-- Commit checkpoint: tasks 5+ -->
```

## Kanban Task Example (replaces lee-to's TaskCreate)

```text
hermes kanban --board departments create "Implement user login endpoint" \
  --assignee aif_implementer --priority 5 --parent <plan_task_id> \
  --project <slug> \
  --body "Create POST /api/auth/login endpoint that:
- Accepts email and password
- Validates credentials against database
- Returns JWT token on success
- Returns 401 on invalid credentials

LOGGING REQUIREMENTS:
- Log function entry with request context
- Log validation result (pass/fail with reasons)
- Log external service calls and responses
- Log any errors with full context
- Use format: [ServiceName.method] message {data}
- Use log levels (DEBUG/INFO/WARN/ERROR)

Files: src/api/auth/login.ts, src/services/auth.ts

Plan: .hermes-dev/plans/<slug>.md (Task 3)"
```

## Logging Requirements Checklist

Every task description should specify:
- What to log: inputs, outputs, state changes, errors
- Where to log: key checkpoints and external boundaries
- Levels: DEBUG for verbose flow, INFO for major events, ERROR for failures
- Control: environment-driven (`LOG_LEVEL` or `DEBUG`)
- Safety: production log level can be reduced without code edits

Never create tasks without logging instructions.
