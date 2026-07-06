# Reference: Test Plan (test-plan)

> **When to use:** When invoked with the `test-plan` argument (or as the second stage of `--all`).

---

## Step 1: Verify Previous Stage Artifact

Use the `resolved_branch`, `artifact_dir`, and artifact language resolved in SKILL.md Step 0 and Step 0.2.

Check for the file `<artifact_dir>/change-summary.md`.

**If the file is NOT found — STOP.** A test plan cannot be created without a change summary:
- Worker: `kanban_block` with "change-summary.md missing — run aif-qa change-summary <resolved_branch> first".
- Interactive: explain the missing artifact and offer to run `aif-qa change-summary <resolved_branch>` first, or cancel.

Do not continue until the artifact is created.

**If the file is found** — read `<artifact_dir>/change-summary.md` and use it as the basis for the test plan. Proceed to Step 2.

---

## Step 2: Clarify Context

Only if something is not obvious from the code and change-summary:

- What feature or fix was implemented?
- Are there existing test cases for this area?
- What environment is available for testing?
- Are there constraints or dependencies to account for?

**Interactive sessions** may ask the user these questions. **Skip this step when `all_mode = true` or running as a kanban worker** — proceed with what is available from the change-summary and codebase context, and mark assumptions explicitly.

## Step 3: Define Test Scope

Based on the change analysis, determine:

**In Scope** — what we test:

- Directly changed functionality
- Adjacent components with high regression risk
- Integration points affected by the changes

**Out of Scope** — what we don't test:

- Unrelated functionality
- Components without changes and without dependencies on changed ones

Render these headings and descriptions in the resolved artifact language in the saved artifact.

## Step 4: Define Test Types

Use functional, regression, edge-case, negative, security, and performance categories when relevant. If the artifact language is not English, translate human-readable type labels and priority labels, keeping common technical terms in English when that is clearer for the project audience.

## Step 5: Build the Verification Checklist

Describe checks as a checklist with priority labels (high / medium / low). Write the checklist in the resolved artifact language.

## Step 6: Generate the Test Plan

Use the canonical English template `templates/TEST-PLAN.md` as the structure source. If the artifact language is not English, translate all human-readable headings, labels, checklist items, placeholders, enum labels, priority labels, and explanatory text before saving. Keep file paths, commands, code identifiers, branch names, config keys, API names, package names, and raw error messages unchanged.

Use the change summary evidence when prioritizing checks. If a high-priority test is based on an assumption rather than observed code/diff evidence, mark that assumption explicitly.

## Step 7: Save Artifact

Before saving:
- Verify that the document is written in the resolved artifact language; if most headings or body text are in another language, rewrite it before saving.
- Technical identifiers, code names, branch names, API names, CLI commands, file paths, config keys, and raw error messages stay unchanged.

Save the result to `<artifact_dir>/test-plan.md`.

## Step 8: Next Step

**If `all_mode = true` (always true for kanban workers)** — do NOT show any prompt. Proceed directly to `references/TEST-CASES.md`.

**Otherwise (interactive):** tell the user the test plan was saved and ask whether to proceed to writing test cases (run `aif-qa test-cases <resolved_branch>`) or stop here.
