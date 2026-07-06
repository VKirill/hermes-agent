# aif-plan Examples

Ported from lee-to AI Factory `/aif-plan`, adapted to Hermes. Differences that shape
these examples: there is no fast/full mode split and no `--parallel` / `--list` /
`--cleanup` worktree subcommands (Hermes projects own worktrees and branches), no
`.ai-factory/config.yaml` (paths are fixed under `.hermes-dev/`), and kanban workers
are autonomous — where lee-to asked the user, the Hermes skill proceeds on evidence
or blocks the kanban task with the exact reason. Interactive (topic / Claude Code)
use may still ask.

## Input parsing

### Kanban worker (default)

```text
hermes kanban --board departments show <id>
-> description = task body + parent handoffs
-> settings (Testing / Logging / Docs) read from the task body;
   unstated -> defaults: Testing no (unless the task asks for tests),
   Logging verbose, Docs no
```

### Interactive (topic / CLI session)

```text
"plan: Add user authentication with OAuth"
-> description = "Add user authentication with OAuth"
-> interactive use MAY ask 1-2 clarifying questions before planning;
   worker mode never asks (block instead, see Scenario 6)
```

### Description omitted (defaults from research)

```text
(empty task body / bare "plan")
-> description defaults to the Active Summary Topic of
   .hermes-dev/research/RESEARCH.md (written by aif-explore), if present
-> worker mode with no body AND no research file -> block the kanban task:
   "planning input missing: empty task body and no
    .hermes-dev/research/RESEARCH.md to plan from"
```

## Flow scenarios

### Scenario 1: Small change to an existing app

```text
Task: "Add product search API" (project: shop-api)

-> Step 0: load DESCRIPTION.md + ARCHITECTURE.md (project root), .hermes-dev/RULES.md,
   skill-context/aif-plan/SKILL.md if present
-> Reconnaissance + requirement analysis
-> Creates 4 tasks (each with deliverable, file paths, logging requirements)
-> Saves plan to ~/Work/apps/shop-api/.hermes-dev/plans/product-search-api.md
-> Completes the planning kanban task with a structured handoff
   (plan path, task count, downstream assignee aif_implementer)
-> STOP — the planner never implements the plan itself
```

### Scenario 2: Feature epic with a kanban role chain

```text
Task: "Add user authentication with OAuth (tests: yes, logging: verbose, docs: yes)"

-> Reconnaissance, deep codebase exploration
-> Plan slug: user-authentication
-> Creates 8 tasks with commit checkpoints every 3-5 tasks
-> Saves plan to .hermes-dev/plans/user-authentication.md
-> Wires the downstream chain (native handoff, no HANDOFF_MODE):
   hermes kanban --board departments create "Implement: user authentication" \
     --assignee aif_implementer --priority 5 --parent <plan_task_id> \
     --body "<scope + files + logging + acceptance>"
   hermes kanban --board departments link <impl_id> <verify_id>
   hermes kanban --board departments link <verify_id> <review_id>
-> Completes the planning task; aif_implementer picks up next
```

### Scenario 3: New application (bootstrap, Step 3.5)

```text
Task: "New app: парсер цен конкурентов"

-> Slug: parser-cen-konkurentov
-> mkdir -p ~/Work/apps/parser-cen-konkurentov/.hermes-dev/{plans,specs,contracts,gates,rules,skill-context}
-> git -C ~/Work/apps/parser-cen-konkurentov init -q
-> hermes project create "Парсер цен конкурентов" --slug parser-cen-konkurentov \
     --primary ~/Work/apps/parser-cen-konkurentov --board departments
-> Implementation tasks anchored with --project parser-cen-konkurentov
-> Plan saved to ~/Work/apps/parser-cen-konkurentov/.hermes-dev/plans/parser-cen-konkurentov.md
```

### Scenario 4: Sequential plan numbering (project rule)

```text
.hermes-dev/RULES.md contains:
  "Plan files use a 4-digit sequential prefix: NNNN_<slug>.md"
.hermes-dev/plans/ already contains:
  0001_admin-auth.md
  0002_admin-design.md
  0003_admin-bootstrap.md

Task: "Add user authentication with OAuth"

-> Plan slug: user-authentication
-> Next number: max(0001, 0002, 0003) + 1 = 0004
-> Saves plan to .hermes-dev/plans/0004_user-authentication.md

# If the directory is empty, the same flow starts from 0001.
# Only .hermes-dev/plans/ counts — plans archived by aif-archive under
# .hermes-dev/archive/plans/ never influence the numbering.
# Numbers are derived from existing files: deleting 0004_*.md frees the 0004
# slot for the next run. Keep prior plans in place if you rely on stable
# cross-references.
```

### Scenario 5: 9999 cap (block, don't improvise)

```text
.hermes-dev/plans/9999_alpha.md exists and the sequential rule is active

-> The 4-digit space is exhausted: 9999 is a strict cap, because consumer
   globs in aif-implement / aif-verify are also 4-digit
-> Abort BEFORE writing any plan file: never write 10000_*.md, never reuse
   or overwrite 9999_*.md, never silently fall back to another number
-> Block the kanban task citing the 9999 cap (suggest archiving old plans
   via aif-archive or dropping the sequential rule)
```

### Scenario 6: Missing input (block, don't guess)

```text
Task: "Improve the thing we discussed" (no spec, no parent handoff, no research)

-> Requirements are ambiguous and cannot be recovered from
   .hermes-dev/ artifacts or parent tasks
-> hermes kanban --board departments block <id> \
     --reason "planning input missing: no spec/brief in the task body, no
     parent handoff, no .hermes-dev/research/RESEARCH.md; need: <exact ask>"
-> Never fabricate scope to keep the pipeline moving
```
