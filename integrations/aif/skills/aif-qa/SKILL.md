---
name: aif-qa
description: >-
  QA workflow for testing a feature or task implementation: analyze changes and risks
  (change-summary), build a structured test plan (test-plan), and describe concrete
  manual test scenarios (test-cases). Emits the department gate_result (gate "qa").
  Use when a change needs QA, or the user says "test this", "write test plan",
  "what should I test", "QA this branch". Port of lee-to AI Factory /aif-qa,
  adapted to Hermes.
tags:
  - aif
  - qa
  - testing
  - quality-gate
  - dev-factory
  - kanban
---

# aif-qa — Implementation Testing (QA gate)

Generates change summaries, produces test plans, and describes test scenarios for a feature or task implementation. Downstream, `aif-qa-check` executes the produced test cases.

## Hermes context

- Runs as a kanban worker (QA gate stage) or interactively. **No `HANDOFF_MODE`, no `.ai-factory/config.yaml`** — paths are fixed:
  - QA artifacts: `.hermes-dev/qa/<branch-slug>/` (`change-summary.md`, `test-plan.md`, `test-cases.md`)
  - Project context: `DESCRIPTION.md`, `ARCHITECTURE.md` (project root)
  - Project rules for this skill: `.hermes-dev/skill-context/aif-qa/SKILL.md`
- **Autonomous:** kanban workers run the full `--all` pipeline without inter-stage prompts and apply the documented non-interactive defaults; they block only when change context genuinely cannot be established. Interactive (topic/CLI) sessions may ask, as marked in the references.
- **Gate skill:** emits the department gate_result contract (gate `"qa"`) — see "Gate result" below and `aif-methodology` for the full contract.

## Modes

The skill operates in three sequential modes.

| Argument         | Mode           | What you do                                                      |
|------------------|----------------|------------------------------------------------------------------|
| `change-summary` | Change summary | Analyze what changed, assess risks, produce a summary            |
| `test-plan`      | Test plan      | Create a structured test plan based on the change summary        |
| `test-cases`     | Test cases     | Describe concrete test scenarios based on the plan               |
| `--all`          | Full pipeline  | Run all three modes in sequence without prompting between stages |

Kanban workers default to `--all` when the task body does not name a specific mode.

---

## Workflow

### Step 0: Load context and settings

Fixed settings (no config file in Hermes):
- `qa_root = .hermes-dev/qa/`
- `git_enabled = true` unless the workspace is not a git work tree or the task body says otherwise
- `base_branch = main` unless the task body / project docs name a different base

**Artifact language:** artifacts are written in English by default. If the kanban task, the topic conversation, or project context explicitly requests another language (e.g. Russian), translate all human-readable prose — headings, labels, checklist items, placeholders, enum/risk/priority labels, test names, steps, expected results, and explanatory text — into that language before saving. ALWAYS preserve markdown structure, table shapes, checkbox syntax, test case IDs (`TC-001`), code identifiers, file paths, commands, branch names, config keys, API names, package names, and raw error messages unchanged. Keep common technical terms (`commit`, `branch`, `diff`, `endpoint`, `payload`, `rollback`, `regression`, `fixture`) when that is clearer for the project audience. User-visible messages follow the language of the conversation.

The canonical English templates in `templates/*.md` define structure, not language — never save a non-English artifact with English headings left verbatim.

If `git_enabled = false` or the current directory is not a git work tree, do not run git diff/log commands. Use manual change context mode instead: take the change context from the kanban task body / parent handoffs (pasted diff, changed file list, or implementation description); interactive sessions may ask the user for one of these. If no change context can be established at all — worker: `kanban_block` with the exact missing input; interactive: ask or cancel.

### Step 0.1: Load project context

**Read** `DESCRIPTION.md` (project root) if it exists: tech stack (language, framework, database, ORM), project architecture and coding conventions, non-functional requirements.

**Read** `ARCHITECTURE.md` (project root) if it exists: chosen architecture pattern, folder structure conventions, layer/module boundaries and dependency rules.

Use this context when generating summaries, test plans, and test cases.

**Read `.hermes-dev/skill-context/aif-qa/SKILL.md`** — MANDATORY if the file exists. It contains project-specific rules accumulated by `aif-evolve`. Treat them as **project-level overrides**: on conflict with this SKILL.md, the skill-context rule wins; otherwise apply both.

### Step 0.2: Parse arguments and resolve branch

Parse the invocation arguments (or kanban task body) fully before doing anything else:

1. **Detect `--all` flag** — if present, set `all_mode = true` and remove the flag from arguments
2. **Detect mode** — first word matching `change-summary`, `test-plan`, or `test-cases`; remove it from arguments
3. **Detect branch** — remaining text (if any) is the target branch name

**Resolve the working branch:**

```text
If git_enabled = false or the repository is not a git work tree:
  If branch was provided in arguments → use it as the resolved branch label
  Otherwise → set resolved_branch = "manual"
  Use manual change context mode for analysis
If git_enabled = true and the repository is a git work tree:
  If branch was provided in arguments → use it as the resolved branch
  Otherwise → run: git branch --show-current
```

Store both values for use in all reference files:
- `resolved_branch` — the branch being analyzed (used to locate/save artifacts)
- `artifact_dir` — `<qa_root>/<branch-slug>`, where `branch-slug` is a deterministic, filesystem-safe, collision-resistant slug derived from `resolved_branch`. Compute it in three steps:
  1. **Safe slug.** Take `resolved_branch` and replace every character that is not in `[A-Za-z0-9._-]` with `-`, collapse runs of consecutive `-` into a single `-`, and trim leading/trailing `-`. If the result is empty, use `branch`. Then MUST truncate to the first 40 ASCII characters. Because the normalized `safe_slug` alphabet is `[A-Za-z0-9._-]`, byte length and character length are identical. Call this `safe_slug`.
  2. **Hash suffix.** Run `git hash-object --stdin <<< "<resolved_branch>"` and take the **first 8 hex characters** of the output. Call this `hash8`. The hash is derived from the **original, unnormalized** branch name so branches that collapse to the same `safe_slug` still produce different derived slugs in normal use.
  3. **Combine:** `branch-slug = "<safe_slug>-<hash8>"`.

  **Why the hash:** a readable slug alone is lossy — `feature/foo` and `feature-foo` normalize to the same `safe_slug` and would overwrite each other's artifacts. Appending a short hash of the full original name keeps the derived slug stable, readable, and collision-resistant.

  **Examples:**
  - `feature/foo` → `safe_slug=feature-foo`, `hash8=a72ccce7` → `feature-foo-a72ccce7`
  - `feature-foo` → `safe_slug=feature-foo`, `hash8=6f80dfc6` → `feature-foo-6f80dfc6`
  - `main` → `safe_slug=main`, `hash8=<computed>` → `main-<hash8>`
- `all_mode` — whether to skip inter-stage prompts

**If no mode was provided and `all_mode = false`:** worker → set `all_mode = true` (full pipeline); interactive → ask which mode to run (change summary / test plan / test cases / full pipeline).

### Step 1: Execute the selected mode

The skill runs **strictly sequentially** — each stage uses the artifact from the previous one:

```text
change-summary → test-plan → test-cases
```

Read the detailed instructions for the selected mode:

- **Change summary** (`change-summary`) → read `references/CHANGE-SUMMARY.md`
- **Test plan** (`test-plan`) → read `references/TEST-PLAN.md`
- **Test cases** (`test-cases`) → read `references/TEST-CASES.md`

**Full pipeline (`--all`):** run all three modes in sequence. After each stage completes successfully, proceed to the next automatically — **do NOT show the inter-stage prompt**:

```text
1. Execute change-summary (references/CHANGE-SUMMARY.md) → save artifact
2. Execute test-plan      (references/TEST-PLAN.md)      → save artifact
3. Execute test-cases     (references/TEST-CASES.md)     → save artifact
4. Emit gate_result; interactive sessions also get the context cleanup prompt (Step 6 of TEST-CASES.md)
```

If any stage fails (e.g. git error, diff too large and the source is unusable) — stop the pipeline and report which stage failed (worker: `kanban_block` naming the stage and the exact reason).

---

## Principles

### DO:

- Understand the subject before writing test plans and test cases (analyze changes / test plan / merge request / task / text description)
- Use the repository code only to the extent needed for the change analysis, test plan, and test cases
- Write steps clearly enough that any tester can execute the test without knowledge of the codebase
- Specify concrete test data, not abstract "enter valid data"
- Prioritize — not everything is equally important
- Think about adjacent systems, integrations, and dependencies
- Include negative scenarios and edge cases — they catch most bugs
- Interactive sessions: ask clarifying questions when business logic is not obvious from the code. Workers: proceed on code evidence and mark assumptions explicitly in the artifact

### DO NOT:

- Replace the manual QA plan with automated test implementation details
- Make assumptions about business logic without reading the code
- Skip negative scenarios
- Write test cases for everything — focus on risky areas
- Ignore data edge cases

You may mention existing automated checks only as supporting verification; the primary output must remain manual QA scenarios.

---

## Priority reference

| Priority | When to use                                                                     |
|----------|---------------------------------------------------------------------------------|
| High     | Core business logic, user data, payments, security, authorization               |
| Medium   | Supporting functionality, UI/UX, reports, integrations                          |
| Low      | Cosmetic changes, rare scenarios, nice-to-have                                  |

## Gate result

As a gate skill, finish the kanban run by emitting **exactly one** machine-readable gate_result block (schema in `aif-methodology` — do not restate it) and pass it via `kanban_complete` (pass/warn) or `kanban_block` (fail):

- `gate`: `"qa"`
- `status: "pass"` — all requested artifacts produced, grounded in observed code/diff evidence
- `status: "warn"` — artifacts produced but with explicitly marked assumptions (e.g. manual mode without a reliable file list, truncated commit scope)
- `status: "fail"` — change context could not be established or a pipeline stage failed; `blockers` name the stage and the exact missing input
- `affected_files`: the analyzed changed files; `suggested_next`: `{ "action": "aif-qa-check", "reason": "Test cases ready for execution." }` on pass/warn, `/aif-fix` or the missing-input owner on fail

## Artifact ownership

- Primary ownership: QA artifacts under `.hermes-dev/qa/<branch-slug>/` — specifically `change-summary.md`, `test-plan.md`, and `test-cases.md`. The `--all` flag respects the same boundary.
- Write policy: persistent writes are limited to the three owned artifacts above; no other files are created or modified.
- `DESCRIPTION.md`, `ARCHITECTURE.md`, skill-context, and repository code are read-only context.

## Critical rules

1. MUST NOT create a `test-plan` without a `change-summary` artifact
2. MUST NOT create `test-cases` without a `test-plan` artifact
3. MUST NOT skip stages
4. Every high-risk finding MUST be backed by observed code/diff evidence or explicitly marked as an assumption
5. Workers MUST NOT stall on inter-stage prompts — `--all` semantics apply; block only for genuinely missing change context
