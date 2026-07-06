# Reference: Change Summary (change-summary)

> **When to use:** When invoked with the `change-summary` argument (or as the first stage of `--all`). Also run this mode first when the change context is unknown — before writing a test plan or test cases.

---

## Step 1: Gather Change Information

Use the `resolved_branch`, `artifact_dir`, artifact language, `git_enabled`, and `base_branch` resolved in SKILL.md Step 0 and Step 0.2.

### Manual Change Context

If `git_enabled = false`, the current directory is not a git work tree, or required refs cannot be resolved, do not fail with a raw git error.

Obtain change context from one of these sources (kanban workers: take it from the task body and parent handoffs; interactive sessions: ask the user):
1. A pasted diff or PR description
2. A changed-file list
3. A short implementation summary

Use the supplied context as the primary evidence source. If no context source is available — worker: `kanban_block` naming the exact missing input; interactive: stop without writing an artifact if the user cancels.

If an explicit changed-file list is provided, use it as `changed_files` for Step 2.
If you only have a diff, derive `changed_files` from the touched paths in that diff.
If you only have a PR description or short implementation summary, derive a best-effort `changed_files` list from any explicitly named files, modules, routes, commands, or components mentioned there.
If no reliable file list can be derived, skip file exploration in Step 2 and continue with summary-level risk analysis based on the supplied evidence. In that case, mark file-level uncertainty explicitly in the generated artifact instead of falling back to git assumptions.

### Git Change Context

Use this flow only when `git_enabled = true` and the repository is a git work tree.

**Resolve the comparison base:**

> Use `base_branch` (default: `main`).
> If `resolved_branch` IS the base branch, set `effective_base = <resolved_branch>~1`.
> Otherwise, set `effective_base = <base_branch>`.
>
> Validate refs before running log or diff commands:
>
> ```bash
> git rev-parse --verify <resolved_branch>
> git rev-parse --verify <effective_base>
> ```
>
> If `<resolved_branch>` resolves locally, set `analysis_target = <resolved_branch>`.
>
> If `<resolved_branch>` is not available locally, try refreshing remotes and then resolve the remote target ref:
>
> ```bash
> git fetch --all --prune
> git rev-parse --verify origin/<resolved_branch>
> ```
>
> If `origin/<resolved_branch>` resolves, set `analysis_target = origin/<resolved_branch>`. Keep `resolved_branch` unchanged as the artifact label, branch slug input, and user-facing command argument. If neither local nor remote target branch resolves, switch to manual change context mode (above) for the comparison source.
>
> If `<effective_base>` is not available locally, try refreshing remotes and then resolve the remote base:
>
> ```bash
> git fetch --all --prune
> git rev-parse --verify origin/<base_branch>
> ```
>
> If `origin/<base_branch>` resolves, set `effective_base = origin/<base_branch>`. If neither local nor remote base resolves, switch to manual change context mode for the comparison source.
>
> Build the full commit range from `effective_base..<analysis_target>`.
> Start with `analysis_base = <effective_base>`.
> This special case stays anchored to `analysis_target`, not to the current checkout.

**Get the full commit list:**

```bash
git log <effective_base>..<analysis_target> --oneline
```

**Check commit count — if more than 20:**

- **Interactive:** tell the user that `<N>` commits were found and ask whether to analyze all commits, only the last 20, or cancel.
- **Worker (non-interactive default):** analyze only the last 20 and record the truncation explicitly in the artifact (this downgrades the gate_result to at most `warn`).

Based on the choice:
- "Analyze all" → keep `analysis_base = <effective_base>`
- "Analyze only the last 20" → select the 20 most recent commits from the full range, find the oldest commit in that subset, and set `analysis_base = <oldest_selected_commit>^`
  - This `^` shorthand uses Git's first-parent semantics for the selected oldest commit.
- "Cancel" (interactive only) → **STOP**

**Finalize the scoped commit list:**

```bash
git log <analysis_base>..<analysis_target> --oneline
```

Use `analysis_base` for the final commit list and for all diff commands below. This keeps the reduced commit scope and diff scope aligned.

**Get diff statistics, changed files, and diff:**

```bash
git diff --stat <analysis_base>...<analysis_target>
git diff <analysis_base>...<analysis_target> --name-status
git diff <analysis_base>...<analysis_target>
```

**Check diff size — if the diff exceeds ~1000 lines:**

- **Interactive:** warn the user (`<N>` lines) and ask whether to read it fully, analyze important files individually (recommended for large diffs), or cancel.
- **Worker (non-interactive default):** skip the raw full diff and read changed files individually (the recommended option).

Based on the choice:
- "Continue" → use the full diff as-is
- "Read files individually" → skip the raw full diff; proceed to Step 2 and read targeted per-file diffs/content
- "Cancel" (interactive only) → **STOP**

For large diffs, never load generated files, lock files, dependency snapshots, build artifacts, minified assets, or vendored code unless the change itself is about them. Start from `git diff --stat`, then `git diff <analysis_base>...<analysis_target> --name-status`, then per-file diffs for important files. Treat deleted and renamed files explicitly: deleted files may indicate removed behavior; renamed files may require caller/import checks even when content is mostly unchanged.

## Step 2: Explore Key Changed Files

**If subagents mode is enabled (department default), spawn `Explore` subagents via the Agent tool to understand the changed files in parallel; in skills mode read the key files directly with Read/Grep.** Parallel exploration keeps the main context clean and speeds up analysis on large diffs.

If Step 1 produced `changed_files`, identify the most important files from that set (focus on business logic, skip lock files, generated files, dependency snapshots, build artifacts, minified assets, vendored code, and formatting-only changes).

If `changed_files` is unavailable because manual mode only provided summary-level context, skip direct file exploration. Instead, summarize risks from the supplied evidence, note that file-level exploration could not be performed, and keep assumptions clearly labeled.

Launch 1–2 Explore subagents simultaneously:

```text
Agent 1 — Core changes:
Agent(subagent_type: Explore, prompt:
  "Read and summarize the key changed files: [list of most important files].
   Focus on: what logic changed, what inputs/outputs changed, what side effects are possible.
   Thoroughness: medium. Be concise.")

Agent 2 — Integration points (if needed):
Agent(subagent_type: Explore, prompt:
  "Find all callers and consumers of [changed modules/functions].
   Identify what adjacent functionality might be affected.
   Thoroughness: quick.")
```

**Fallback:** if the Agent tool is unavailable, read the key files directly using Read/Grep.

After agents return, synthesize findings to understand:
- What business logic actually changed
- What dependent code could be affected
- What integration points are at risk
- Which findings are confirmed by code/diff evidence and which are assumptions

## Step 3: Risk Analysis

For each changed component, assess:

**Functional risks:**

- Did the business logic change?
- Were input/output data affected (formats, validation, structure)?
- Are there dependent modules or components that might break?
- How does the change affect user scenarios?

**Technical risks:**

- Changes to data schema (DB, API contracts, file formats, storage)?
- Changes to configuration or environment variables?
- Changes to error handling or edge case behavior?
- Changes to integrations with external services or APIs?
- Changes to authorization, access control, or security?

**Regression risks:**

- What existing functionality might have broken?
- Which adjacent features need re-verification?

Every high-risk item must be backed by observed code/diff evidence or explicitly marked as an assumption.

## Step 4: Generate the Summary

Use the canonical English template `templates/CHANGE-SUMMARY.md` as the structure source. Write the artifact in the artifact language resolved in SKILL.md Step 0 (English default); if it is not English, translate all human-readable headings, labels, checklist items, placeholders, enum labels, risk labels, and explanatory text before saving, keeping file paths, commands, code identifiers, branch names, config keys, API names, package names, and raw error messages unchanged.

The summary must include an `Evidence` section (localized heading is allowed) that ties important findings to files, functions, commits, or diff observations.

## Step 5: Save Artifact

Before saving:
- Verify that the document is written in the resolved artifact language; if most headings or body text are in another language, rewrite it before saving.
- Technical identifiers, code names, branch names, API names, CLI commands, file paths, config keys, and raw error messages stay unchanged.

**Ensure the directory exists before saving:**

```bash
mkdir -p <artifact_dir>
```

Save the result to `<artifact_dir>/change-summary.md`.

## Step 6: Next Step

**If `all_mode = true` (always true for kanban workers)** — do NOT show any prompt. Proceed directly to `references/TEST-PLAN.md`.

**Otherwise (interactive):** tell the user the change summary was saved and ask whether to proceed to the test plan (run `aif-qa test-plan <resolved_branch>`) or stop here.
