---
name: aif-commit
description: >-
  Commit discipline: create conventional commit messages by analyzing staged changes,
  honor the plan's Commit Plan grouping, split unrelated work, and never push or merge
  without explicit approval. Use when the user says "commit", "save changes", "create
  commit", or a task reaches a commit checkpoint. Port of lee-to AI Factory /aif-commit,
  adapted to Hermes.
tags:
  - aif
  - git
  - commits
  - dev-factory
---

# aif-commit — Conventional Commit Generator

Generate commit messages following the [Conventional Commits](https://www.conventionalcommits.org/) specification, grouped sanely.

## Hermes context

- Runs interactively or inside a kanban worker's task workspace. **No `.ai-factory/config.yaml`** — fixed paths: plans `.hermes-dev/plans/`, rules `.hermes-dev/RULES.md` + `.hermes-dev/rules/*`, `DESCRIPTION.md`/`ARCHITECTURE.md` at the project root, roadmap `.hermes-dev/plans/ROADMAP.md`.
- **Hermes hard rule: NEVER push or merge without explicit human approval.** Local commits inside a task workspace are fine and expected (plan checkpoints). There is no post-commit push prompt: interactive sessions push only when the user explicitly asks in their own words; kanban workers never push — if a task demands a push/merge, block it with the exact reason (irreversible/prod-affecting action needs approval).
- **Autonomy:** workers don't ask. Commit when the message is unambiguous (plan checkpoint message, or a clean staged diff); when grouping is ambiguous, fall back to one commit of all staged changes with the best single message and note it in the handoff — never stall the pipeline over commit granularity. Interactive sessions confirm before committing (see Behavior).

## Step 0 — Load skill context

**Read `.hermes-dev/skill-context/aif-commit/SKILL.md` — MANDATORY if it exists.** Project rules accumulated by `/aif-evolve`; treat as project-level overrides (on conflict, skill-context wins; no conflict → apply both). They apply to ALL outputs including the commit message format ("commits MUST follow format X" → comply). Verify the generated message against these rules before using it — a violating message is a bug.

## Workflow

1. **Analyze changes**
   - `git status` to see staged files; `git diff --cached` to see staged changes.
   - If nothing is staged, show a warning and suggest staging (worker: stage the task's changed files explicitly by path — never `git add -A` blindly).

2. **Resolve active plan context (read-only, optional)**
   - Priority: `@<plan-file>` argument (when the argument starts with `@`) → branch-based plan in `.hermes-dev/plans/` → single plan in `.hermes-dev/plans/`. An argument not starting with `@` stays commit scope/context.
   - Branch-based lookup: `git branch --show-current`, replace every `/` with `-` → `<branch-stem>`; Glob `.hermes-dev/plans/[0-9][0-9][0-9][0-9]_<branch-stem>.md` first (numbered plans; multiple matches → highest-numbered wins, emit `WARN [aif-commit] multiple sequential plans for <branch>: <list>; using <chosen>`); fall back to `.hermes-dev/plans/<branch-stem>.md`.
   - If branch lookup fails, check whether `.hermes-dev/plans/` contains exactly one plan file.
   - If no plan resolves or it has no `## Commit Plan`, keep the plain staged-diff behavior. **Never modify the plan from this skill.**

3. **Use Commit Plan grouping when available**
   - Parse `## Commit Plan`: group number/name, task range (`after tasks 1-3`, `tasks 4-6`), suggested conventional message. Map ranges to task descriptions and `Files:` hints via the plan's `## Tasks` section.
   - Compare staged files/hunks with planned groups **before changing staging**: staged paths from `git diff --cached --name-only`; staged hunk evidence from `git diff --cached` when a file may span groups. Task ranges and `Files:` hints are guidance, not executable instructions.
   - Before whole-file staging, compare grouped files with unstaged worktree paths from `git diff --name-only`. Only use `git add <files>` when each group has a disjoint file set and no grouped file appears in `git diff --name-only`.
   - One file spanning multiple groups → hunk-level staging (`git add -p` or `git apply --cached`) per group. Grouped files overlapping unstaged worktree paths → preserve and re-apply the original cached patch per group (`git diff --cached` + `git apply --cached`), or use hunk-level staging, or stop before changing staging.
   - If files can't be mapped to groups, or hunk-level staging can't be applied confidently: **interactive** — ask the user to adjust grouping or commit everything together; **worker** — commit everything together with one message and note the deviation in the handoff.
   - When a usable grouping exists, **interactive** — ask: Follow Commit Plan / Commit everything together / Adjust grouping (then validate the adjusted grouping against staged files); **worker** — follow the Commit Plan.

4. **Run context gates (read-only)**
   - `ARCHITECTURE.md` + `DESCRIPTION.md` — catch obvious scope/boundary drift. `.hermes-dev/RULES.md` (+ `.hermes-dev/rules/*`) + `.hermes-dev/plans/ROADMAP.md` — rule and milestone alignment; rules hierarchy for commit conventions.
   - Missing optional files (ROADMAP.md, RULES.md) are `WARN`, not blockers. Never modify context artifacts from this skill. Gate labels stay `WARN`/`ERROR` — no implicit strict mode; for a standalone rules pass suggest `aif-rules-check`.

5. **Determine commit type** — `feat` (new feature), `fix` (bug fix), `docs`, `style` (formatting), `refactor` (neither fix nor feature), `perf`, `test`, `build` (build system/deps), `ci`, `chore`.

6. **Identify scope** — from file paths (`src/auth/` → `auth`), or from the argument. Optional — omit when changes span multiple areas.

7. **Generate the message** — subject under 72 chars; imperative mood ("add", not "added"); no capital after the type; no trailing period. If commit type is `feat`/`fix`/`perf` and ROADMAP.md exists, check milestone linkage; if missing, warn and suggest adding it in the body/footer.

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Examples:**

```
feat(auth): add password reset functionality
```

```
fix(api): handle null response from payment gateway

The payment API can return null when the gateway times out.
Added null check and retry logic.

Fixes #123
```

```
feat(api)!: change response format for user endpoint

BREAKING CHANGE: user endpoint now returns nested profile object
```

## Behavior

1. Check staged changes → analyze the diff → resolve optional plan context and use `## Commit Plan` grouping when available → run read-only context gates (summarize findings as `WARN`/`ERROR`) → propose the message.
2. **Interactive:** confirm before committing — "Commit as is / Edit message / Cancel"; on Edit, take the corrected message and re-confirm; on Cancel, stop without committing. **Worker:** commit directly with the generated (or plan-suggested) message.
3. Execute `git commit` with the confirmed message.
4. **After commit: no push.** Show `git status -sb` so the ahead-count is visible. Push/merge only on explicit human request (interactive) — never as an offer, never from a worker.

If an argument is provided (e.g. scope `auth`), use it as the scope or as context for the message.

## Splitting unrelated work

If staged changes contain unrelated work (a feature + a bugfix, or changes to independent modules), suggest splitting:

1. Show which files/hunks belong to which commit.
2. **Interactive** — confirm the split plan: "Yes, split as suggested / No, commit everything together / Let me adjust the grouping" (on adjust, take the new grouping and re-validate against staged files). **Worker** — split only when the mapping is unambiguous; otherwise one commit with a note in the handoff.
3. Before changing staging, confirm: does each group have a disjoint file set; does any file span multiple groups; do grouped files overlap unstaged worktree paths from `git diff --name-only`?
4. Disjoint sets + no overlap with unstaged paths → `git reset HEAD`, then stage and commit each group separately with `git add <files>` + `git commit`.
5. Grouped files overlapping unstaged worktree paths → preserve each group's original cached patch before unstaging and re-apply only that patch with `git apply --cached`; otherwise hunk-level staging, or stop before changing staging.
6. One file spanning groups → hunk-level staging per group (`git add -p` / `git apply --cached`), commit, repeat.
7. If hunk-level staging or cached-patch application can't be applied confidently — interactive: stop and ask; worker: commit everything together and note it.

## Important

- **Never commit secrets or credentials.** Review large diffs carefully before committing.
- **NEVER push or merge without explicit human approval** (Hermes department hard rule; overrides any old auto-push behavior).
- Context gates are warning-first — no implicit strict mode unless the user explicitly requests blocking behavior.
- Treat architecture, roadmap, RULES.md, description, and plan artifacts as read-only context here.
- No active plan / no `## Commit Plan` → plain staged-diff behavior, unchanged.
- NEVER add `Co-Authored-By` or any other trailer attributing authorship to the AI. Commits must not contain AI co-author lines.
