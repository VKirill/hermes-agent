# FIX_PLAN.md template (aif-fix plan-first mode)

The parent skill defers to this document for the fix-plan structure and the Research Context hashing rules so `SKILL.md` stays focused on the workflow. The template defines the **required structure** — fill it with real investigation results, never placeholders.

## Annotation rule

When the plan is created while working a kanban task, the very first line of the file MUST be:

```
<!-- hermes:task:<task_id> -->
```

followed by a blank line, then the plan content. Omitting the annotation when a task id is known is a bug — verify before completing. When re-writing an existing plan, preserve an existing annotation. When there is no kanban context, do not add one.

## Template

```markdown
# Fix Plan: [Brief title]

**Problem:** [What's broken — from the reporter's description]
**Created:** YYYY-MM-DD HH:mm

## Analysis

What was found during investigation:

- Root cause (or suspected root cause)
- Affected files and functions
- Impact scope

## Fix Checklist

1. [ ] Apply the Canonical Regression-First Policy: add or identify the minimal regression check, or record why no useful check exists
2. [ ] Run the regression check and confirm it reproduces the reported problem, or record the fallback outcome from the policy
3. [ ] Implement the smallest fix for the root cause
4. [ ] Rerun the same regression check and confirm it passes when a rerunnable check exists
5. [ ] Run the closest related existing checks when practical

## Files to Modify

- `path/to/file.ts` — what changes are needed
- `path/to/another.ts` — what changes are needed

## Risks & Considerations

- Potential side effects
- Things to verify after the fix
- Edge cases to watch for

## Test Coverage

- Minimal regression check to confirm the bug before implementation
- Command/check to run before and after the fix
- Additional edge cases worth covering after the regression check passes

## Research Context (optional)

Include only when this fix plan is based on `.hermes-dev/research/RESEARCH.md`.
Source: .hermes-dev/research/RESEARCH.md (Active Summary, Updated: YYYY-MM-DD HH:MM, SHA256: <active-summary-sha256>)
```

## Research Context hashing rules

When adding `## Research Context`, copy the relevant Active Summary from `.hermes-dev/research/RESEARCH.md` and record a revision marker so downstream execution can detect drift:

- Normalize the copied text before hashing: include exactly the text pasted under `## Research Context` after the `Source:` line; exclude markdown comments and the `Source:` line itself; preserve line order; trim trailing spaces; use LF line endings; end with exactly one final newline.
- Calculate the digest **without writing any temporary file**: feed the normalized text through stdin / inline shell input to `shasum -a 256`; if `shasum` is unavailable, use `sha256sum`. Use the first output field as the `SHA256:` value.
- If research is unrelated to the bug, omit the section entirely.

Executing against a plan whose source marker is missing or whose current Active Summary differs → emit `WARN [research-drift]` and execute the plan's embedded context; rebase onto newer research only when explicitly asked.

## After creating the plan

Interactive output:

```
## Fix Plan Created ✅

Plan saved to .hermes-dev/fixes/FIX_PLAN.md.

Review the plan and when you're ready to execute, run:

/aif-fix
```

Worker: complete the planning task with a handoff (plan path, root-cause summary, downstream fix task). **STOP — do NOT apply the fix in plan-first mode.**
