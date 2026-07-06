# aif-fix worked examples & output templates

Non-normative reading aid moved out of `SKILL.md`. The templates define structure only.

## Example 1: Null reference error

**Input:** `/aif-fix TypeError: Cannot read property 'name' of undefined in UserProfile`

1. Search for the UserProfile component/function
2. Find where `.name` is accessed
3. Add a regression check for the null user case and confirm it fails
4. Add null check with logging
5. Rerun the same regression check and confirm it passes

## Example 2: API returns wrong data

**Input:** `/aif-fix /api/orders returns empty array for authenticated users`

1. Find the orders API endpoint
2. Trace the query logic
3. Find the bug (e.g., wrong filter)
4. Add or identify an integration regression check for the authenticated user case and confirm it fails
5. Fix with logging
6. Rerun the same regression check and confirm it passes

## Example 3: Form validation not working

**Input:** `/aif-fix email validation accepts invalid emails`

1. Find the email validation logic
2. Check regex or validation library usage
3. Add a unit regression test for the invalid email case and confirm it fails
4. Fix the validation
5. Add logging for validation failures
6. Rerun the same regression test and confirm it passes

## "Fix Applied" output template (Step 5 / completion handoff)

```
## Fix Applied ✅

**Issue:** [what was broken]
**Cause:** [why it was broken]
**Fix:** [what was changed]
**Regression check:** [command/check and result, manual/runtime reproduction result, or "not available: <reason>"]

**Files modified:**
- path/to/file.ts (line X)

**Logging added:** Yes, prefix `[FIX]`

### Recommended: Add More Test Coverage

If a regression check was created in Step 2.5, this bug is now covered.
Consider broader coverage to prevent nearby regressions:

    describe('functionName', () => {
      it('should handle [the edge case that caused the bug]', () => {
        // Arrange — the problematic input
        // Act
        // Assert — the expected behavior
      });
    });
```

Interactive follow-up: ask "Would you like me to create the additional test coverage?" (Yes → create the test file per project conventions, run it, then proceed to the patch step. No → proceed directly to the patch step.) Worker: carry the suggestion in the kanban handoff instead of asking.
