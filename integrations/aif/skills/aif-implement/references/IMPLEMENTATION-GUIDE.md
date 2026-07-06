# Implementation Reference

Ported from lee-to AI Factory `/aif-implement`, adapted to Hermes: plan artifacts
live under `.hermes-dev/`, progress is tracked in plan checkboxes + the kanban task
(no lee-to `TaskList`/`TaskUpdate`), and blockers are handled autonomously
(block-not-ask) — interactive (topic/CLI) sessions may still ask.

## Progress Display Format

```
┌─────────────────────────────────────────────┐
│ Feature: User Authentication                │
├─────────────────────────────────────────────┤
│ ✅ #1 Create user model                     │
│ ✅ #2 Add registration endpoint             │
│ ✅ #3 Add login endpoint                    │
│ 🔄 #4 Implement JWT generation    ← current │
│ ⏳ #5 Add password reset                    │
│ ⏳ #6 Add email verification                │
├─────────────────────────────────────────────┤
│ Progress: 3/6 (50%)                         │
└─────────────────────────────────────────────┘
```

## Handling Blockers

If a task cannot be completed, do NOT stall and do NOT silently skip it. Classify:

1. **Solvable within scope** — a small approach change delivers the same
   deliverable without expanding scope: adjust, note the deviation in the
   handoff, continue.
2. **Blocked by missing context/access or by an irreversible/prod-affecting
   action** (deploy/publish/migrate/spend/force-push/merge): block the kanban
   task with the exact reason and evidence:

```
hermes kanban --board departments block <task_id> \
  --reason "Task #4 blocked: <what failed / what is missing>.
  Tried: <commands + outcomes>. Need: <exact input or approval>."
```

Completed tasks stay marked `- [x]` in the plan so a later session resumes from
the blocker, not from scratch. In interactive sessions you may instead present
the options (skip / modify approach / stop and discuss) and ask.

## Session Continuity

The plan file's checkboxes are the source of truth for progress; the kanban task
(status + comments) carries the cross-session handoff state. Flip `- [ ]` → `- [x]`
immediately after each task — never batch the updates.

## List Available Plans (read-only discovery)

When asked to list plans (interactive `--list`, or a scoped "what plans exist"
task), use read-only discovery and stop without executing any tasks.

### Discovery steps

```
git branch --show-current   # git mode only
```

Then derive, in priority order:
- `handoffPlan` = the plan path named in the kanban task body / parent handoff
  (always wins when present)
- `branchPlan` = `.hermes-dev/plans/<branch-with-slashes-replaced-by-hyphens>.md`
  — with the sequential project rule active, the highest-numbered
  `.hermes-dev/plans/<NNNN>_<stem>.md` match for that stem
- `namedFullPlan` = the only `*.md` file in `.hermes-dev/plans/` when no
  branch-based plan exists
- `fixPlan` = the aif-fix artifact under `.hermes-dev/fixes/`

Check which files exist and print:

```
## Available Plans
Current branch: <branch>
- [x| ] <handoffPlan>   (named in the kanban handoff)
- [x| ] <branchPlan>    (current-branch plan)
- [x| ] <namedFullPlan> (single plan without branch)
- [x| ] <fixPlan>       (fix plan)

Use:
- aif-implement with an explicit plan path to execute a specific plan
- aif-implement with no path to use the automatic priority above
```

If no plans exist, print:

```
No plan files found. Create one with:
- skill aif-plan <description>   (feature/enhancement plans)
- skill aif-fix <bug description> (fix plans)
```

### Constraints

- Do not execute implementation tasks
- Do not modify files
- Do not complete/comment the kanban task as if work was done

## Recovery after a break or a fresh session

If you are resuming without prior conversational context, rebuild context from
git + the plan file before continuing:

```
git status
git branch --show-current
git log --oneline --decorate -20
git diff --stat
```

Then:
- Re-open the active plan file (explicit plan path from the kanban handoff if
  provided; otherwise branch plan first, then a single named plan; a fix plan
  redirects to `aif-fix`).
- Read the kanban task's status and comments for the last recorded state.
- If the kanban state and plan checkboxes disagree, reconcile: verify the code
  is actually there (Glob/Grep/Read), then correct the plan checkbox and note
  the reconciliation in the task comment.

**Starting new session:**
```
Task: continue implementation (plan: .hermes-dev/plans/user-authentication.md)

Agent: Resuming implementation...

Found 3 completed tasks, 5 pending.
Continuing from Task #4: Implement JWT generation

[Executes task #4]
```

## Example Full Flow

```
Session 1 (aif_planner):
  Task "Add user authentication" → skill aif-plan
  → Creates 6 tasks with logging requirements
  → Saves plan to .hermes-dev/plans/user-authentication.md
  → Creates the implement task (assignee aif_implementer) with the plan path
    in the body; links implement → verify → review

Session 2 (aif_implementer):
  → Reads the kanban task + plan .hermes-dev/plans/user-authentication.md
  → Completes tasks #1, #2, #3, flipping each checkbox immediately
  → Session ends (worker timeout / checkpoint commit)

Session 3 (aif_implementer):
  → Re-reads the kanban task; plan shows 3/6 complete
  → Continues from task #4; completes #4, #5, #6
  → All done: kanban complete with evidence (files, commands, outcomes);
    aif_verifier picks up the linked verify task
```
