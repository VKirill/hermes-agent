# Self-improvement patch template (aif-fix Step 6)

Every fix generates a patch under `.hermes-dev/patches/` — this builds the knowledge base that `/aif-evolve` later distills into `skill-context` rules. Patches are **learning artifacts, not reports**.

- Filename: current timestamp, format `YYYY-MM-DD-HH.mm.md` (e.g. `2026-02-07-14.30.md`).
- Create the directory first if missing: `mkdir -p .hermes-dev/patches`.

## Template

```markdown
# [Brief title describing the fix]

**Date:** YYYY-MM-DD HH:mm
**Files:** list of modified files
**Severity:** low | medium | high | critical

## Problem

What was broken. How it manifested (error message, wrong behavior).
Be specific — include the actual error or symptom.

## Root Cause

WHY the problem occurred. This is the most valuable part.
Not "what was wrong" but "why it was wrong":

- Logic error? Why was the logic incorrect?
- Missing check? Why was it missing?
- Wrong assumption? What was assumed?
- Race condition? What sequence caused it?

## Solution

How the fix was implemented. Key code changes and reasoning.
Include the approach, not just "changed line X".

## Prevention

How to prevent this class of problems in the future:

- What pattern/practice should be followed?
- What should be checked during code review?
- What test would catch this?

## Tags

Space-separated tags for categorization, e.g.:
`#null-check` `#async` `#validation` `#typescript` `#api` `#database`
```

## Example patch

```markdown
# Null reference in UserProfile when user has no avatar

**Date:** 2026-02-07 14:30
**Files:** src/components/UserProfile.tsx
**Severity:** medium

## Problem

TypeError: Cannot read property 'url' of undefined when rendering
UserProfile for users without an uploaded avatar.

## Root Cause

The `user.avatar` field is optional in the database schema but the
component accessed `user.avatar.url` without a null check. This was
introduced in commit abc123 when avatar display was added — the
developer tested only with users that had avatars.

## Solution

Added optional chaining: `user.avatar?.url` with a fallback to a
default avatar URL. Also added a null check in the Avatar sub-component.

## Prevention

- Always check if database fields marked as `nullable` / `optional`
  are handled with null checks in the UI layer
- Add test cases for "empty state" — user with minimal data
- Consider a lint rule for accessing nested optional properties

## Tags

`#null-check` `#react` `#optional-field` `#typescript`
```
