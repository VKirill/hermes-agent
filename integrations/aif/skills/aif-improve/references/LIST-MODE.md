# `--list` mode procedure

This file describes the read-only plan discovery procedure that runs when `aif-improve` is invoked with the `--list` flag. The parent skill defers to this document instead of inlining the procedure, because `--list` is a conditional branch and keeps the main `SKILL.md` body within the size limit.

The examples and output shapes in this reference define structure only.

## When this runs

`aif-improve --list` is invoked. The flag may appear anywhere in the arguments. When `--list` is present, this procedure runs to completion and the skill stops — no refinement is performed even if other tokens (`+check`, `@path`, free-form prompt) are also passed. Those tokens are silently ignored in `--list` mode.

## Procedure

1. **Get the current branch** (git repos only):

   ```bash
   git branch --show-current
   ```

2. **Convert the branch name to a filename stem**: replace `/` with `-`. The result is `<branch-slug>`. Example: `feature/user-auth` → `feature-user-auth`.

3. **Check existence of every plan location below** (paths are fixed in Hermes — there is no config file):

   - `.hermes-dev/plans/<branch-slug>.md` (the default slug convention from `aif-plan`).
   - Numbered sequential plans: glob `.hermes-dev/plans/[0-9][0-9][0-9][0-9]_<branch-slug>.md` and report all matches with the highest-numbered match first. (Hermes has no `plan_id_format` config flag — sequential naming is auto-detected from the filenames themselves.)
   - If the workspace is not a git repo or has no current branch, list every `*.md` file in `.hermes-dev/plans/` that looks like a full plan. A leading 4-digit prefix counts as a match.
   - The fix plan at `.hermes-dev/fixes/FIX_PLAN.md` (from `aif-fix` plan mode).

4. **Print the availability summary**, followed by usage hints the user can copy verbatim. Example output shape:

   ```
   ## Available Plans
   Current branch: feature/user-auth

   - [x] .hermes-dev/plans/feature-user-auth.md
   - [ ] .hermes-dev/fixes/FIX_PLAN.md

   Use:
   - /aif-improve @<path> <optional prompt>
   - /aif-improve <optional prompt>      # automatic priority
   ```

   - Mark each candidate with `[x]` when it exists and `[ ]` when it does not.
   - Show paths relative to the project root.

5. **If no plan exists at any of the locations above**, suggest creating one:

   ```
   No plans found. Create one first:
   - /aif-plan <description>       — feature/enhancement plan
   - /aif-fix <bug description>    — bugfix plan (plan-first mode)
   ```

6. **Archived plans.** If `.hermes-dev/archive/plans/` exists and contains `*.md` files, display a separate count line after the main list: `Archived plans: N (in .hermes-dev/archive/plans/)`. Do not list individual archived plans — use `/aif-archive list` for that.

7. **STOP.** Do not proceed to any refinement step.

## Read-only contract

In `--list` mode the skill MUST NOT:

- modify any files,
- create or delete any plans,
- create, update, or complete kanban tasks or plan checkboxes,
- call the validator subagent (the `+check` flag is silently ignored — there is nothing to validate before refinement runs).

Only `git` (read-only), `Read`, `Glob`, and `Grep` are required to satisfy the procedure above.

## Example

```
User: /aif-improve --list

## Available Plans
Current branch: feature/user-auth
- [x] .hermes-dev/plans/feature-user-auth.md
- [x] .hermes-dev/fixes/FIX_PLAN.md

Use:
- /aif-improve @.hermes-dev/plans/feature-user-auth.md
- /aif-improve add validation and retries
```
