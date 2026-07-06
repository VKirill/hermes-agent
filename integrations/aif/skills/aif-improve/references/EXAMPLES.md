# `aif-improve` worked examples

This file collects the worked examples that previously lived inline in `SKILL.md`. The parent skill defers to this document so the main file stays under the soft skill-size budget; the examples themselves are non-normative and exist as a reading aid.

The examples and output shapes in this reference define structure only.

The `--list` mode example lives in `references/LIST-MODE.md`. The `+check` mode example lives in `references/CHECK-MODE.md` — these two are not duplicated here.

## Example 1: Auto-review (no arguments)

```
User: /aif-improve

→ Found plan: .hermes-dev/plans/feature-user-auth.md
→ 6 tasks in plan
→ Deep codebase analysis...
→ Found: project uses middleware pattern for auth, plan misses middleware task
→ Found: Task #3 description doesn't mention existing UserService
→ Found: Task #5 depends on Task #3 but no dependency set

Report:
- 1 missing task (auth middleware)
- 1 task to improve (reference UserService)
- 1 dependency to fix

Apply? → Yes → Changes applied
```

## Example 2: With user prompt

```
User: /aif-improve add error handling and input validation

→ Found plan: .hermes-dev/plans/feature-user-auth.md
→ 4 tasks in plan
→ User wants: error handling + input validation
→ Analyzing each task for missing error handling...
→ Found: none of the tasks mention input validation
→ Found: error handling is inconsistent

Report:
- 2 tasks improved (added validation details to descriptions)
- 1 new task (create shared validation utils)
- Updated task descriptions with error handling patterns from codebase

Apply? → Yes → Changes applied
```

## Example 3: No plan found

```
User: /aif-improve

→ Branch: <current-branch-or-empty>
→ No matching branch-based plan found in .hermes-dev/plans/
→ No fix plan at .hermes-dev/fixes/FIX_PLAN.md
→ No plan file found

"No active plan found. Create one first:
- /aif-plan <description>
- /aif-fix <bug description>"
```

(Kanban worker mode: block the task with the same "no active plan found" reason instead of printing a suggestion.)

## Example 4: Explicit plan file

```
User: /aif-improve @my-custom-plan.md add rollback and edge-case handling

→ Explicit plan override: my-custom-plan.md
→ Found plan: my-custom-plan.md
→ User wants: rollback + edge-case handling
→ Deep codebase analysis...
→ Report prepared
```

## Example 5: Plan already looks good

```
User: /aif-improve

→ Found plan: .hermes-dev/plans/feature-product-search.md
→ 5 tasks in plan
→ Deep analysis... all tasks well-defined, dependencies correct
→ No significant improvements found

"Plan looks solid! Ready to implement:
/aif-implement"
```

## Report section prose shapes (Step 5)

Reference wording for the four prose-shaped groups (behavioral impact → optional note → plan anchor → suggested edit):

```
#### 🆕 Missing Tasks (N found)
1. The plan currently leaves authenticated requests without a session refresh step — long-running clients silently lose access after the access-token TTL. The existing middleware in `src/middleware/auth.ts` already exposes a `refresh()` hook, so the plan should reuse it instead of inventing a new one. After Task #3. Add a new task: "Wire `authMiddleware.refresh()` into the login flow and cover the expired-token path with an explicit test."

#### 📝 Task Improvements (N found)
1. Task #4 ("Add validation") gives no field-by-field contract — implementer will either over-validate or skip the email format check that the rest of the codebase enforces via `validators/email.ts`. Task #4. Rewrite as: "Validate `email` (via `validators/email.ts`), `password` (min 12 chars), and `displayName` (1-64 chars) in `RegisterRequest`; return 422 with field-level errors when validation fails."

#### 🔗 Dependency Fixes (N found)
1. Task #5 should depend on Task #2. Reason: Task #5 consumes the session helper introduced in Task #2.

#### 🗑️ Removals (N found)
1. Task #7 ("Create UserRepository") duplicates `src/repos/user.ts:12` which already exposes the same query surface — keeping the task will lead to a parallel implementation. Task #7. Remove the task; rely on the existing repository and adjust Task #8 to import it.

#### 💡 Out of scope — for later (N found)
1. Task #11 ("Refactor the logging module") looks reasonable on its own but is unrelated to the login feature this plan is about — keeping it expands scope without any concrete trigger from the current code paths. Task #11. Drop it from the active plan; the idea is surfaced here so you can capture it elsewhere (issue tracker, backlog note) if it's worth revisiting as its own feature later.
```
