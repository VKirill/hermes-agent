[← Development Workflow](workflow.md) · [AIF methodology](../../SKILL.md) · [Skill Evolution →](evolve.md)

> Ported from lee-to AI Factory `docs/skills.md`. Adaptations: `/aif-x` slash commands → `aif-x`
> skills (workers load skills by name; slash still works in interactive Claude Code sessions);
> `.ai-factory/config.yaml` reads replaced by fixed paths and Step 0 context loading;
> `language.*` semantics dropped (see [Config Reference](config-reference.md)).

# Core Skills

There is no per-project config file in Hermes. Instead, every `aif-*` skill starts with a
**Step 0 context load** from fixed locations: `DESCRIPTION.md` / `ARCHITECTURE.md` / `AGENTS.md`
at the project root, the rules hierarchy under `.hermes-dev/`, and — mandatory when it exists —
its own `.hermes-dev/skill-context/<skill>/SKILL.md` (project rules accumulated by `aif-evolve`;
on conflict skill-context wins).

Repo-driven skills that need little shared context: `aif-best-practices`, `aif-build-automation`,
`aif-ci`, `aif-dockerize`, `aif-grounded`, `aif-skill-generator` (lee-to's "config-agnostic" set).

## Workflow Skills

These skills form the core development loop. See [Development Workflow](workflow.md) for the full
diagram and how they connect.

### `aif-explore [topic or plan name]`
Explore ideas, constraints, and trade-offs before planning:
```
aif-explore real-time collaboration
aif-explore the auth system is getting unwieldy
aif-explore add-auth-system
```
- Uses a thinking-partner mode: open questions, option mapping, and ASCII visualization
- Reads project context from DESCRIPTION.md, ARCHITECTURE.md, rules, and research artifacts plus
  active plan files when present
- Does **not** implement code in this mode; when direction is clear, move to `aif-plan`
- Can optionally persist exploration context to `.hermes-dev/research/RESEARCH.md` so a later
  session or pipeline stage can feed results into `aif-plan` (uses `aif:active-summary` markers)
- Best when the problem is still fuzzy: requirements unclear, trade-offs unresolved, or you want
  to inspect the codebase before choosing a direction

### `aif-plan <description>`
Plans implementation for a feature or task:
```
aif-plan Add user authentication with OAuth
```

- Explores the codebase for patterns, creates tasks with dependencies, includes commit checkpoints
  for 5+ tasks
- Saves the plan to `.hermes-dev/plans/<slug>.md` (lee-to's fast/full modes both land here; the
  distinction only affects question depth and branch creation)
- Asks about testing/logging/docs policy (interactive) or derives it from the task body (worker)
- Step 3.5 bootstraps brand-new apps: `~/Work/apps/<slug>/` + `.hermes-dev/` scaffold + git init +
  `hermes project create`
- In the kanban pipeline, planning ends with a structured handoff to `aif_implementer` — the
  planner never implements

If the user supplied a planning request, `aif-plan` saves it verbatim in the plan file as
`Original Request`. This block is raw source input, not generated prose; downstream plan rewrites
must preserve it exactly. It is omitted only when the plan is created solely from `RESEARCH.md`
without an explicit user request.

If `.hermes-dev/research/RESEARCH.md` exists, `aif-plan` may read the `Active Summary` as optional
context. It includes `Research Context` only when research content influenced the generated plan.
Linked plans include a `Source:` reference with revision metadata so downstream skills treat the
embedded context as committed requirements and warn if live research has drifted.

If `.hermes-dev/plans/ROADMAP.md` exists, `aif-plan` may also capture a `Roadmap Linkage` section
(milestone name + brief rationale) to make milestone alignment explicit.

**Parallel mode** — work on multiple features simultaneously using `git worktree`
(interactive sessions; in the kanban pipeline parallelism is handled by separate cards and, when
delegation is enabled, by `implement-coordinator` dispatching parallel workers):
```
aif-plan full --parallel Add Stripe checkout
```
- Creates a separate working directory (`../my-project-feature-stripe-checkout`)
- Copies AI context files (`.hermes-dev/`, root context files)
- Each feature gets its own session — no branch switching, no conflicts

**Manage parallel features:**
```
aif-plan --list                            # Show all active worktrees
aif-plan --cleanup feature/stripe-checkout # Remove worktree and branch
```

### `aif-roadmap [check | vision or requirements]`
Creates or updates a strategic project roadmap:
```
aif-roadmap                              # Analyze project and create roadmap
aif-roadmap SaaS for project management  # Create roadmap from vision
aif-roadmap                              # Update existing roadmap
aif-roadmap check                        # Auto-scan codebase, mark done milestones
```
- Reads DESCRIPTION.md and ARCHITECTURE.md for context
- **First run** — explores codebase, collects major goals, generates `.hermes-dev/plans/ROADMAP.md`
- **Subsequent runs** — review progress, add milestones, reprioritize, mark completed
- **`check`** — automated progress scan: analyzes codebase for evidence of completed milestones,
  reports done/partial/not started, marks completed with confirmation (interactive) or evidence
  logging (worker)
- Milestones are high-level goals (not granular tasks — that's `aif-plan`)
- `aif-implement` automatically marks roadmap milestones done when work completes

### `aif-improve [--list] [+check] [@plan-file] [prompt]`
Refine an existing plan with a second iteration:
```
aif-improve                                    # Auto-review: find gaps, missing tasks, wrong deps
aif-improve --list                             # Show available plans only (no refinement)
aif-improve +check                             # Validate refinements via fresh-context subagent
aif-improve @my-custom-plan.md                 # Improve an explicit plan file
aif-improve add validation and error handling  # Improve based on specific feedback
```
- Plan source priority: `@plan-file` argument, then branch-based `.hermes-dev/plans/<branch>.md`,
  then a single named full plan in `.hermes-dev/plans/`, then `.hermes-dev/fixes/FIX_PLAN.md`
- `--list` mode is read-only: shows available plan files and exits
- Performs deeper codebase analysis than the initial `aif-plan` planning
- Treats `## Original Request` as the immutable original intent / scope anchor and preserves it
  verbatim on every plan edit or regeneration
- Preserves embedded `Research Context` as committed requirements, checks the research file for
  revision drift, and emits `WARN [research-drift]` instead of applying newer research silently
- Finds missing tasks (migrations, configs, middleware)
- Fixes task dependencies and descriptions
- Removes redundant tasks
- Surfaces useful-but-out-of-scope tasks in a separate "Out of scope" report section (the skill
  does not save them anywhere)
- Shows an improvement report before applying (interactive: asks for approval; worker: applies and
  records the report)
- If no plan found — suggests running `aif-plan` (feature/task) or `aif-fix` (bugfix) first

**Optional validation (`+check`)**
- After Step 4 the skill dispatches a single fresh-context validator subagent (Agent tool) that
  re-reads cited files and judges each finding from the `missing`, `improvements`, `removals`, and
  `out_of_scope` groups
- Invented findings disappear, partially-correct ones are rewritten in place, real findings stay
  untouched; the `Dependency Fixes` group is recomputed against the filtered task list afterwards
  and is not sent to the validator
- The Step 5 Summary block gains two extra lines — `Hidden by +check: N` and `Adjusted by +check: M`;
  if the validator call fails entirely, no counters are printed and a single `WARN [+check]` line
  is appended instead
- `+check` together with `--list` is silently ignored (no refinement to validate)
- In the kanban pipeline this skill is the optional `improve` stage
  (`kanban.run_plan_improve`)

### `aif-loop [new|resume|status|stop|list|history|clean] [task or alias]`
Runs a strict iterative Reflex Loop with phase-based execution and quality gates:
```
aif-loop new OpenAPI 3.1 spec + DDD notes + JSON examples
aif-loop resume
aif-loop status
aif-loop stop
aif-loop list
aif-loop history courses-api-ddd
aif-loop clean courses-api-ddd
```
- Uses 6 phases: PLAN → PRODUCE||PREPARE → EVALUATE → CRITIQUE → REFINE (PRODUCE and PREPARE run
  in parallel via the Agent tool when subagents mode is enabled)
- Evaluation uses weighted rules with score formula and severity levels (`fail`, `warn`, `info`)
- Persists state between sessions in `.hermes-dev/loop/`:
  - `current.json` (active loop pointer to current run)
  - `<alias>/run.json` (single source of truth for current state)
  - `<alias>/history.jsonl` (append-only event log)
  - `<alias>/artifact.md` (latest artifact output)
- `list` shows all loop runs, `history` shows event timeline, `clean` removes
  stopped/completed/failed loop runs
- Default `max_iterations` is `4`
- Before iteration 1, pins success criteria and max iterations (interactive: explicit user
  confirmation; worker: derived from task text + logged)
- Stops on threshold reached, no major issues, iteration limit, stagnation, or explicit stop
- If stopped by `iteration_limit` with unmet criteria, final summary includes distance-to-success
  (threshold gap + remaining fail-rule blockers)
- Full protocol and schemas: [Reflex Loop](loop.md)

### `aif-implement`
Executes the plan:
```
aif-implement                     # Continue from where you left off
aif-implement --list              # Show available plans only (no execution)
aif-implement @my-custom-plan.md  # Execute using an explicit plan file
aif-implement 5                   # Start from task #5
aif-implement status              # Check progress
aif-implement --without-plan add GET /healthz returning {"status":"ok"}  # Inline one-shot task
```
- **Reads skill-context first** (`.hermes-dev/skill-context/aif-implement/SKILL.md`) and only uses
  limited recent patch fallback when needed
- Finds the plan file (`@plan-file` if provided; otherwise branch-based
  `.hermes-dev/plans/<branch>.md`, then a single named full plan in `.hermes-dev/plans/`, then
  `.hermes-dev/fixes/FIX_PLAN.md` → redirects to `aif-fix`)
- Treats `## Original Request` as original scope context while executing the task list and
  committed `Research Context` as the executable plan inputs; checks the research file only for
  revision drift
- `--list` mode is read-only: shows available plan files and exits
- `--without-plan <description>` mode (inline):
  - Executes exactly one small task from the description — no plan file created, read, or updated
  - Mutually exclusive with `@plan-file`, `status`, and task id
  - Skips checkbox updates, does **not** create `FIX_PLAN.md` or patch entries (use `aif-fix` for
    bugs, not this flag)
  - Loads the same project context as regular mode (DESCRIPTION.md, ARCHITECTURE.md, rules,
    skill-context)
  - Tests are written only if the description explicitly asks, or existing project conventions /
    touched code paths clearly require them
  - Redirects to `aif-plan` when the description looks too broad for a one-shot task
  - Optional `--docs=yes|no|warn` (default: `warn`) — `yes` runs the docs checkpoint via
    `aif-docs`, `no` silences the warn line, `warn` emits `WARN [docs]` only
- Executes tasks one by one with commit checkpoints
- Docs policy after completion (plan-backed modes):
  - `Docs: yes` → mandatory documentation checkpoint (update docs / create feature page / skip)
  - `Docs: no` or unset → `WARN [docs]` only (no mandatory checkpoint)
  - Docs updates are always routed through `aif-docs`
- When subagents mode is enabled (department default), execution runs through
  `implement-coordinator` with quality sidecars (`review-sidecar`, `security-sidecar`,
  `rules-sidecar`, `best-practices-sidecar`, `docs-auditor`, `commit-preparer`); in skills mode
  the worker executes inline — see [Subagents](subagents.md)

### `aif-verify [--strict]`
Verifies completed implementation against the plan:
```
aif-verify          # Check all tasks were fully implemented
aif-verify --strict # Strict mode — zero tolerance before merge
```

In the kanban pipeline this is the `verify` stage (role `aif_verifier`,
`kanban.run_post_verify`); interactively it is the recommended step after `aif-implement`.

- **Task completion audit** — goes through every task in the plan, uses `Glob`/`Grep`/`Read` to
  confirm the code actually implements each requirement. Reports `COMPLETE`, `PARTIAL`, or
  `NOT FOUND` per task
- **Original request context** — uses `## Original Request` as the original scope context when
  present, while the task list and committed `Research Context` remain the executable verification
  inputs
- **Research-backed plan audit** — verifies against embedded `Research Context` when present,
  checks the research file for revision drift, and emits `WARN [research-drift]` instead of
  applying newer Active Summary requirements silently
- **Build & test check** — runs the project's build command, test suite, and linters on changed files
- **Consistency checks** — searches for leftover `TODO`/`FIXME`/`HACK`, undocumented environment
  variables, missing dependencies, plan-vs-code naming drift
- **Context gates (read-only)** — checks architecture/roadmap/rules alignment before final status;
  missing optional roadmap/rules files are warnings
- **Git-aware diffing** — uses the detected base branch for branch-diff verification; no-git
  repositories fall back to recent commits / working tree
- **Issue remediation** — if issues are found: interactive sessions suggest `aif-fix <issue
  summary>`; in the pipeline a FAIL gate_result spawns the fix task automatically
- **Follow-up** — if all green, `aif-security-checklist` and `aif-review` come next, then `aif-commit`
- **Machine-readable result** — emits the `gate_result` (gate `verify`) with
  `status: pass|warn|fail`, `blocking`, `blockers`, `affected_files`, and `suggested_next`

**Strict mode** (`--strict`) is recommended before merging: requires all tasks complete, build
passing, tests passing, lint clean, zero TODOs in changed files, and passing
architecture/rules/roadmap gates. For `feat`/`fix`/`perf`, missing roadmap milestone linkage is
reported as a warning, not a failure.

### `aif-fix [bug description]`
Bug fix with optional plan-first mode:
```
aif-fix TypeError: Cannot read property 'name' of undefined
```
- Two modes: **Fix now** (immediate) or **Plan first** (review before fixing); interactive use
  asks, worker mode picks from the task
- Investigates the codebase to find root cause
- When a bug needs regression coverage, follows the Canonical Regression-First Policy before
  implementation: create or identify a regression check, handle no-regression-check or
  non-reproducible fallbacks, then preserve the same check for verification (policy defined in
  `~/.hermes/skills/aif-fix/SKILL.md`)
- Applies fix WITH logging (`[FIX]` prefix for easy filtering)
- Reruns the same regression check after the fix when available, then suggests any useful extra
  coverage
- Creates a **self-improvement patch** in `.hermes-dev/patches/`
- In the kanban pipeline, gate-FAIL fix tasks are created with idempotency-key `fix:<id>` and
  linked for re-review — this skill closes the review→fix loop

**Plan-first mode** — for complex bugs or when you want to review the approach:
- Investigates the codebase, creates `.hermes-dev/fixes/FIX_PLAN.md` with analysis, fix checklist,
  risks
- Includes `Research Context` only when research content influenced the fix plan, records a
  committed source revision, and checks the live research file only for drift before executing
- Stops after creating the plan — review at your own pace
- When ready, run without arguments to execute:
```
aif-fix    # reads the fix plan → applies fix → deletes only the default FIX_PLAN.md
```
- After successful execution, `aif-fix` deletes only the default `.hermes-dev/fixes/FIX_PLAN.md`;
  custom/non-default fix plan files are preserved

### `aif-evolve [skill-name|"all"]`
Self-improve skills based on project experience:
```
aif-evolve          # Evolve all skills
aif-evolve fix      # Evolve only the aif-fix skill
aif-evolve all      # Evolve all skills (explicit)
```
- Reads patches incrementally from `.hermes-dev/patches/` using
  `.hermes-dev/evolution/patch-cursor.json` (first run reads all)
- Analyzes project tech stack, conventions, and codebase patterns
- Identifies gaps in existing skills (missing guards, tech-specific pitfalls)
- Proposes targeted improvements (interactive: with user approval; worker: conservative defaults +
  full report in the evolution log)
- Writes project-specific overrides to `.hermes-dev/skill-context/<skill>/SKILL.md` (skills treat
  these as higher-priority rules)
- Saves the evolution log to `.hermes-dev/evolution/`
- The more `aif-fix` patches you accumulate, the smarter `aif-evolve` becomes

---

## Utility Skills

### `aif`
Analyzes your project and sets up context:
- Scans project files to understand the codebase
- Checks `~/.hermes/skills/` for relevant existing skills; recommends generating missing ones via
  `aif-skill-generator` (third-party additions go through the [Security](security.md) review)
- Generates the architecture document via `aif-architecture`
- For a **new** app: scaffolds `~/Work/apps/<slug>/` + `.hermes-dev/`, inits git, registers the
  Hermes project on the departments board

When called with a description:
```
aif project management tool with GitHub integration
```
- Creates `DESCRIPTION.md` (project root) with an enhanced project specification
- Creates `ARCHITECTURE.md` (project root) with architecture decisions and guidelines
- Creates `AGENTS.md` and `.hermes-dev/rules/base.md` from codebase evidence
- Transforms your idea into a structured, professional description

**Does NOT implement your project** — only sets up context.

### `aif-grounded <question or task>`
Reliability gate that prevents guessing:
```
aif-grounded Explain how feature flags work in this codebase
aif-grounded Update dependencies to the latest secure versions (no assumptions)
```
- Only provides a final answer if confidence is **100/100** based on evidence (repo files, command
  output, provided docs)
- If confidence is < 100, returns **INSUFFICIENT INFORMATION** with a concrete checklist of what's
  needed to reach 100
- Forces verification for changeable facts ("latest", "current", version-specific behavior)
- Best when the task is already clear but the answer must be strictly verified: high-stakes
  questions, version-sensitive facts, or any prompt that says "no assumptions"

#### `aif-explore` vs `aif-grounded`

| Skill | Use it for | Output style | If things are unclear |
|-------|------------|--------------|------------------------|
| `aif-explore` | discovery, requirement shaping, trade-off discussion, repo investigation before planning | open-ended thinking partner | keeps exploring, reframing, and comparing options |
| `aif-grounded` | evidence-only answers, strict verification, high-stakes or changeable facts | confidence-gated answer with explicit evidence | stops and returns `INSUFFICIENT INFORMATION` |

Typical sequence when both are useful:
1. `aif-explore` — figure out what problem you are really solving.
2. `aif-grounded` — verify the important claims or current-state facts.
3. `aif-plan` — turn the clarified, verified direction into executable tasks.

### `aif-architecture [explicit|structured|microservices|layers]`
Generates architecture guidelines tailored to your project:
```
aif-architecture                     # Analyze project and recommend
aif-architecture explicit-layers     # Explicit Architecture (Technical Layer)
aif-architecture explicit-vertical   # Explicit Architecture (Vertical Slices By Entity)
aif-architecture explicit-flat       # Explicit Architecture (Flat Vertical Slice - Simplified)
aif-architecture explicit            # Choose among the 3 explicit variants
aif-architecture structured-layers   # Structured Modules (Technical Layer)
aif-architecture structured-vertical # Structured Modules (Vertical Slices By Entity)
aif-architecture structured          # Choose the folder structure variant
```
*Note: `clean`, `ddd`, `monolith`, and `vertical` are legacy aliases mapped to current patterns.*
- Reads `DESCRIPTION.md` for project context
- Recommends an architecture pattern based on team size, domain complexity, and tech stack
- Generates `ARCHITECTURE.md` (project root) with folder structure, dependency rules, code examples
- All examples adapted to your project's language and framework
- Called automatically by `aif` during setup, but can also be used standalone

### `aif-docs [--web]`
Generates and maintains project documentation:
```
aif-docs          # Generate or improve documentation
aif-docs --web    # Also generate HTML version in docs-html/
```

**Smart detection** — adapts to your project's current state:
- **No README?** — analyzes the codebase and creates a lean README (~100 lines) as a landing page +
  a `docs/` directory with topic pages
- **Long README?** — proposes splitting into a landing-page README with detailed content moved to
  `docs/`
- **Docs exist?** — audits for stale content, broken links, missing topics, outdated formatting

**Scattered .md cleanup** — finds loose markdown files in the project root (CONTRIBUTING.md,
SETUP.md, DEPLOYMENT.md, etc.) and proposes consolidating them into `docs/`. Guard: the root
context files `DESCRIPTION.md`, `AGENTS.md`, `ARCHITECTURE.md` are NOT "scattered docs" — they
stay at the root by convention.

**Stays in sync with your code** — when the plan sets `Docs: yes`, `aif-implement` shows a
mandatory docs checkpoint and routes changes through `aif-docs`. If `Docs: no` (or unset),
`aif-implement` emits `WARN [docs]` so potential drift is visible without blocking the flow.

**Documentation website** — `--web` generates a complete static HTML site in `docs-html/` with
navigation, dark mode support, and clean typography.

**Quality checks:**
- Every doc page in `docs/` gets prev/next navigation + "See Also" cross-links
- Technical review — verifies links, structure, code examples, no content loss
- Readability review — "new user eyes" checklist: is it clear, scannable, jargon-free?

### `aif-dockerize [--audit]`
Generates, enhances, or audits Docker configuration:
```
aif-dockerize          # Auto-detect mode based on existing files
aif-dockerize --audit  # Force audit mode on existing Docker files
```

**Three modes** (auto-detected):
1. **Generate** — no Docker files exist → infrastructure choices (DB, reverse proxy, cache), then
   create everything from scratch
2. **Enhance** — only local Docker exists → audit & improve local, then create production config
   with deploy scripts
3. **Audit** — full Docker setup exists → run security checklist, fix gaps, add missing best
   practices

**Generated file structure:**
- Root: `Dockerfile`, `compose.yml`, `compose.override.yml`, `compose.production.yml`,
  `.dockerignore`, `.env.example`
- `docker/` — service configs (angie/, postgres/, php/, redis/) — only directories that are needed
- `deploy/scripts/` — 6 production ops scripts: deploy, update, logs, health-check, rollback,
  backup (with tiered retention). Scripts are **generated**; executing them against production is
  an irreversible action → block for human approval (department policy)

**Security audit** — production checklist (OWASP Docker Security Cheat Sheet): container isolation
(read-only, no-new-privileges, cap_drop, non-root, tmpfs), port exposure, network security, health
checks, log rotation, resource limits, secrets management, image pinning, over-engineering check.

After completion, suggests `aif-build-automation` and `aif-docs`.
Supports Go, Node.js, Python, and PHP with framework-specific configurations.

### `aif-build-automation [makefile|taskfile|justfile|mage]`
Generates or enhances build automation files:
```
aif-build-automation              # Auto-detect or ask which tool
aif-build-automation makefile     # Generate a Makefile
aif-build-automation taskfile     # Generate a Taskfile.yml
aif-build-automation justfile    # Generate a justfile
aif-build-automation mage         # Generate a magefile.go
```

**Two modes — generate or enhance:**
- **No build file exists?** — analyzes the project and generates a complete, best-practice build
  file from scratch
- **Build file already exists?** — scans for gaps (missing targets, no help command, no Docker
  targets despite Dockerfile, missing preamble) and enhances it surgically, preserving structure

**Project detection (all stacks):** one **ordered pipeline** for every ecosystem: primary language
→ package manager / build entrypoints → frameworks → Docker → CI → migrations → tests → linters &
formatters → monorepo signals, producing a `PROJECT_PROFILE`.

**Docker-aware** — container lifecycle targets (`docker-build`, `docker-push`, `docker-logs`),
dev vs production separation, `infra-up`/`infra-down` for dependency services, container-exec
variants for Docker-first projects.

**Post-generation integration:** updates README and existing docs with a quick command reference,
suggests recording build commands in `AGENTS.md`, updates markdown files that already list
project commands.

**Stack support:** Go, Node.js, Python, PHP, Rust (`Cargo.toml`), Ruby (`Gemfile`), plus
Java/Kotlin (Gradle/Maven) with framework-specific targets per `PROJECT_PROFILE`.

### `aif-ci [github|gitlab] [--enhance]`
Generates, enhances, or audits CI/CD pipeline configuration:
```
aif-ci                   # Auto-detect platform and mode
aif-ci github            # Generate GitHub Actions workflow
aif-ci gitlab            # Generate GitLab CI pipeline
aif-ci --enhance         # Force enhance mode on existing CI
```

**Three modes** (auto-detected): Generate (no CI config), Enhance (CI incomplete — add missing
lint/SA/security jobs), Audit (full setup — check best practices, fix gaps). Actions that touch
**live CI** (e.g. triggering pipelines, changing protected settings) are block-not-ask in worker
mode.

**One workflow per concern** — separate files, not a monolith: `lint.yml`, `tests.yml`,
`build.yml`, `security.yml`.

**Per-language tools detected automatically:** PHP (PHP-CS-Fixer/Pint/PHPCS, PHPStan/Psalm,
Rector, PHPUnit/Pest), Python (Ruff/Black+isort+Flake8, mypy, pytest, bandit; uv and pip),
Node.js/TypeScript (ESLint/Prettier/Biome, tsc, Jest/Vitest), Go (golangci-lint, go test,
govulncheck), Rust (cargo fmt, clippy, cargo test, cargo audit/deny), Java
(Checkstyle/PMD/SpotBugs, JUnit, OWASP).

**CI best practices built-in:** concurrency groups, `fail-fast: false`, dependency caching,
GitLab `policy: pull` + DAG with `needs:`, GitHub explicit `permissions` +
dependency-review-action, service containers when tests need them.

After completion, suggests `aif-build-automation` and `aif-dockerize`.

### `aif-rules [rule text]`
Adds project-specific rules and conventions:
```
aif-rules Always use DTO instead of arrays
aif-rules                                    # Interactive — asks what to add
aif-rules area:api                           # Create area-specific rules
```
- Rules are saved to `.hermes-dev/RULES.md` as the axioms artifact
- **Area rules:** `area:api`, `area:frontend`, `area:backend` — creates
  `.hermes-dev/rules/<area>.md` (discovered by filename; no config registration in Hermes)
- **Rules hierarchy:** `rules/<area>.md` > `rules/base.md` > `RULES.md`
- Rules are automatically loaded by `aif-implement` before task execution
- Use for coding conventions, naming rules, architectural constraints

### `aif-commit`
Creates conventional commits:
- Analyzes staged changes
- Uses active plan `## Commit Plan` groups when available and either follows them, commits
  everything together, or adjusts grouping
- Stops when staged files or hunks cannot be mapped to planned commit groups
- Uses hunk-level staging for planned groups that share a file, or stops before changing staging
  when hunks cannot be applied confidently
- Avoids whole-file staging when there is unstaged worktree overlap with grouped files
- Keeps current staged-diff behavior unchanged when no active plan or no `## Commit Plan` exists
- Generates a meaningful conventional-commit message
- Runs read-only architecture/roadmap/rules gate checks before the commit proposal
- Warning-first by default (no implicit strict mode)
- For `feat`/`fix`/`perf`, warns when roadmap milestone linkage is missing
- **Never pushes or merges without human approval** (Hermes department policy)

### `aif-review [PR number or URL] [+check]`
Reviews staged changes or PR diffs:
```
aif-review
aif-review 123
aif-review https://github.com/org/repo/pull/123
aif-review +check                              # Validate findings via fresh-context subagent
aif-review 123 +check
```
- Checks correctness, security, performance, and maintainability
- Adds read-only context-gate findings (architecture/roadmap/rules) to review output
- Uses `WARN` for non-blocking context drift and `ERROR` only for explicitly blocking review criteria
- Emits the `gate_result` (gate `review`) for the kanban workflow core
- If you only need the rules gate, use `aif-rules-check`

**Optional validation (`+check`)**
- After the review is drafted, a single fresh-context validator subagent re-reads cited files and
  judges each item from "Critical Issues" and "Suggestions"
- Invented findings are dropped, partially-correct ones rewritten in place, real findings stay
  untouched; "Questions" and "Positive Notes" are not validated
- The subagent can reclassify items between the two severity levels — promote a suggestion to
  "Critical Issues" if the behavior is actually merge-blocking, or demote a critical finding to
  "Suggestions" if the framing was too harsh. Definitions and promotion/demotion rules live in
  `~/.hermes/skills/aif-review/references/SEVERITY.md`
- The `gate_result` is recomputed **after** filtering — post-filter findings merged with the
  unchanged context-gate result, so a failing architecture/rules/roadmap gate still forces `fail`
  even when no Critical Issues remain; `suggested_next` is recomputed accordingly (`aif-commit`
  when no blockers remain; otherwise `aif-fix`, or the failing gate's own skill — `aif-rules`,
  `aif-architecture`, `aif-roadmap` — when a single context gate is the sole blocker)
- The rendered review gains a final line `Filtered: N hidden, M adjusted, K reclassified by
  +check`; if the validator call fails entirely, the unfiltered review is kept and a single
  `WARN [+check]` line is appended instead (the gate_result stays the last thing in the output)

### `aif-rules-check [git ref]`
Runs a standalone read-only rules compliance gate:
```
aif-rules-check
aif-rules-check main
```
- Resolves the rules hierarchy from the fixed locations (`.hermes-dev/RULES.md`,
  `.hermes-dev/rules/`)
- Checks staged changes, working-tree diff, or a provided git ref against the resolved rules
- Uses human standalone verdicts: `PASS` when checked rules are satisfied, `WARN` when rules are
  missing/ambiguous or no changed files are available, `FAIL` only for explicit hard-rule
  violations tied to rule text
- Output sections: overall verdict, files checked, gate results, blocking violations, suggested
  fixes, suggested rule updates, and the final `gate_result` (gate `rules`)
- Remains read-only; if rules need to change, route that through `aif-rules`

### `aif-archive [list | --roadmap | --all | <plan-name>]`
Archives completed plans and trims closed roadmap milestones:
```
aif-archive                    # Scan for completed plans, choose which to archive
aif-archive list               # Show archived plans and roadmap snapshots
aif-archive --all              # Archive all completed plans (with confirmation)
aif-archive --roadmap          # Trim closed milestones from ROADMAP.md into a snapshot
aif-archive feature-auth       # Archive a specific plan by name or partial stem
```
- A plan is "completed" when all checkboxes in its `## Tasks` section are `- [x]`
- Preserves original filenames when moving to `.hermes-dev/archive/plans/`
- Adds `archived: YYYY-MM-DD` to the plan's YAML frontmatter
- Archived plans are excluded from plan discovery by `aif-implement`, `aif-verify`, `aif-improve`
- Does not touch fix plans (`.hermes-dev/fixes/FIX_PLAN.md`)
- `--roadmap` creates a dated snapshot under `.hermes-dev/archive/roadmap/` and removes closed
  milestones from `.hermes-dev/plans/ROADMAP.md` (with confirmation)

### `aif-reference <url|path> [url2|path2] [--name <ref-name>] [--update]`
Creates knowledge references from external sources for AI agents:
```
aif-reference https://zod.dev --name zod-validation
aif-reference https://docs.astro.build/en/getting-started/ https://docs.astro.build/en/guides/content-collections/
aif-reference ./docs/api-spec.yaml --name internal-api
aif-reference --update --name zod-validation
aif-reference list
aif-reference show zod-validation
```
- Fetches URLs (with automatic sub-page crawling, up to 8 pages per source), processes local
  files, or searches the web
- Synthesizes structured reference documents: overview, core concepts, API/interface, usage
  patterns, configuration, best practices, pitfalls
- Saves to `.hermes-dev/reference/<name>.md` with source attribution and timestamps
- Maintains an index in `.hermes-dev/reference/INDEX.md`
- `--update` re-fetches sources and refreshes an existing reference
- `list` / `show <name>` / `delete <name>` for managing existing references
- References are available to all AIF skills — `aif-plan`, `aif-implement`, `aif-grounded` can
  read them for domain context
- Best when AI needs knowledge it wasn't trained on: new libraries, internal APIs,
  project-specific specs, or rapidly changing documentation

### `aif-distillation <path|url> [...] [--name <skill-name>] [--path <directory>] [--update] [--redact-source-map] [--split|--split-by <strategy>]`
Distills books, documents, folders, or URLs into one reusable Agent Skill or a split set of
focused skills:
```
aif-distillation ./books/software-craft.pdf --name construction-practices
aif-distillation ./docs/internal-platform ./examples --name platform-operator
aif-distillation https://example.com/guide --name example-api
aif-distillation ./new-material --name platform-operator --update
aif-distillation ./books/code-quality.pdf --split --name code-quality
aif-distillation ./docs/review-playbook --split-by workflow --name review
aif-distillation ./books/internal-guide.pdf --name review-guide --redact-source-map
aif-distillation ./books/ddd.pdf --name ddd-practices --path ./distilled-skills
```
- Accepts local files, directories, and URLs, including large PDFs through a chunking helper
  (script `material-prep.py`; `.hermes`/`.hermes-dev` are in its SENSITIVE_DIR_NAMES guard)
- Saves the distilled package in `~/.hermes/skills/<skill-name>/` by default;
  `--path <directory>` overrides the output root
- Produces a compact `SKILL.md` plus detailed `references/` and practical `examples/`
- Converts source material into workflows, heuristics, checklists, pitfalls, and examples rather
  than a long summary
- `--redact-source-map` skips `SOURCE-MAP.md` and source-map sections entirely, so exact source
  titles, URLs, local paths, repository paths, and filenames are not written to generated files
- `--split` creates several focused child skills under the resolved output root;
  `--split-by auto|goal|topic|workflow|audience` controls boundary selection
- Split children always share one namespace prefix to avoid collisions; child suffixes should
  describe user goals and actions, not source themes (`refactoring-review`, `test-design`,
  `decision-brief`, `incident-triage`, …)
- For programming material, creates adapted code examples (before/after snippets, code patterns)
- Checks existing references/examples before writing and updates matching files instead of
  creating duplicates; in split update mode, matches proposed children against existing sibling
  skills
- Uses temporary extraction artifacts for large material and removes them after generation

### `aif-skill-generator`
Generates new skills:
```
aif-skill-generator project-api
```
- Creates SKILL.md with proper frontmatter, output to `~/.hermes/skills/<name>/`
- Follows the Agent Skills specification
- Can include references, scripts, templates
- Verify the result is visible via `hermes skills list`

**Learn Mode** — pass URLs to generate skills from real documentation:
```
aif-skill-generator https://docs.example.com/tutorial/
aif-skill-generator https://docs.example.com/guide https://docs.example.com/reference
aif-skill-generator my-skill https://docs.example.com/api
```
- Fetches and deeply studies each URL
- Enriches with web search for best practices and pitfalls
- Synthesizes a structured knowledge base
- Generates a complete skill package with references from real sources
- Supports multiple URLs, mixed sources (docs + blogs), and optional skill name hint

### `aif-security-checklist [category]`
Security audit based on OWASP Top 10 and best practices:
```
aif-security-checklist                  # Full audit
aif-security-checklist auth             # Authentication & sessions
aif-security-checklist injection        # SQL/NoSQL/Command injection
aif-security-checklist xss              # Cross-site scripting
aif-security-checklist csrf             # CSRF protection
aif-security-checklist secrets          # Secrets & credentials
aif-security-checklist api              # API security
aif-security-checklist infra            # Infrastructure & headers
aif-security-checklist prompt-injection # LLM prompt injection
aif-security-checklist race-condition   # Race conditions & TOCTOU
```

Each category includes a checklist, vulnerable/safe code examples, and an automated audit script
(`scripts/audit.sh`). API/client checks include production-only safeguards for browser logging and
normalized client-safe UI errors instead of raw exception details. Never read, exfiltrate, or echo
actual secret values — report the location and the risk only.

Audit outputs emit the `gate_result` (gate `security`) for full and category audits. The
`ignore <item>` writer flow updates `.hermes-dev/SECURITY.md` and only reports a gate result when
it also performs an audit.

**Ignoring items** — if a finding is intentionally accepted, mark it as ignored:
```
aif-security-checklist ignore no-csrf
```
- Records the reason in `.hermes-dev/SECURITY.md`
- Future audits skip these items but still show them in an **"Ignored Items"** section for
  transparency
- Review ignored items periodically — risks change over time

### `aif-qa [--all] [change-summary | test-plan | test-cases] [<branch>]`

Three-stage QA workflow for manual testing of a feature or fix:

```
aif-qa change-summary          # Analyze what changed on current branch
aif-qa change-summary feat/x   # Analyze a specific branch
aif-qa test-plan               # Create test plan (requires change-summary artifact)
aif-qa test-cases              # Write test cases (requires test-plan artifact)
aif-qa --all                   # Run all three stages in sequence
aif-qa --all feat/x            # Full pipeline for a specific branch
```

Each stage builds on the previous one and saves its artifact to `.hermes-dev/qa/<branch-slug>/`:

| Stage            | Artifact            | What it produces                                    |
|------------------|---------------------|-----------------------------------------------------|
| `change-summary` | `change-summary.md` | Risk-annotated summary of git changes               |
| `test-plan`      | `test-plan.md`      | Scoped test plan with types and acceptance criteria |
| `test-cases`     | `test-cases.md`     | Concrete TC-NNN scenarios with steps and test data  |

For large branches the `change-summary` stage checks commit count (>20) and diff size (>1000
lines) before proceeding — both gates ask how to continue rather than silently truncating
(worker: block with the size report). When git refs cannot be resolved, `aif-qa` uses manual
change context instead of failing on git commands.

The `--all` flag runs all three stages in sequence without inter-stage prompts. If any stage
fails, the pipeline stops and reports the failing stage. Emits the `gate_result` (gate `qa`).

### `aif-qa-check [human | agent] [<branch>]`

Executes test cases created by `aif-qa test-cases` and records results:

```
aif-qa-check human          # One manual test case at a time
aif-qa-check agent          # Agent runs browser, CLI, API, test, or file checks
aif-qa-check human feat/x   # Use QA artifacts for a specific branch
```

Modes:

| Mode | Behavior |
|------|----------|
| `human` | Shows one `TC-NNN` case at a time, asks whether it works, checks passed cases, and records failed comments from the user after mandatory redaction of sensitive values |
| `agent` | Automated execution through the appropriate surface for each case: browser, CLI, API, automated tests, or file/document checks. Browser/UI cases require live browser execution (Playwright MCP or an in-app browser when available); non-browser cases must not be blocked just because browser automation is unavailable. Reads reusable QA agent context/history first, resolves missing URL/login/access/route/selector/command/fixture information before blocking recoverable cases, offers human-mode continuation only for human-verifiable blocked cases, and requires explicit authorization for unknown/production targets and destructive or external-side-effect cases |

Results are saved to `.hermes-dev/qa/<branch-slug>/qa-check.md`. Passed cases are checked, failed
or blocked cases stay unchecked with comments. The source `test-cases.md` remains read-only.
Current results are bound to the tested commit SHA plus working tree digest (or a manual
build/version identifier when git is unavailable), plus the full `test-cases.md` digest and
per-case digests; stale results are not counted as current after the branch, dirty working tree,
or source cases change. Browser evidence, command output summaries, API observations, file checks,
and human-entered failure comments are redacted before they are persisted. Emits the `gate_result`
(gate `qa-check`).

Agent mode also maintains `.hermes-dev/qa/agent-context.md` and
`.hermes-dev/qa/agent-history.md` as cross-QA memory, not per-run logs. `agent-context.md` stores
curated non-sensitive facts that unblock future automated QA runs (stable target URLs, safe
command patterns, reusable test-filter conventions, login route, test account role, seed data
patterns, stable selectors, field IDs). `agent-history.md` is append-only reusable learning for
recurring blockers, resolved friction, command patterns, navigation notes, and selector
discoveries. Branch names, QA target paths, `TC-*` mappings, summary counts, assertion totals, and
one-off command transcripts stay in branch-specific `qa-check.md`. Secrets such as passwords,
tokens, cookies, authorization headers, one-time codes, and token-bearing URLs must be redacted or
omitted.

Internal deterministic checks (service-method outputs, cache/materialized data behavior, formula
results, raw database invariants, CLI internals) are treated as automated checks: find and run an
existing narrow test or command; when it passes, the corresponding `TC-*` is marked `Passed` with
the command/test evidence. If coverage is missing, block with a missing-automated-coverage note
instead of asking a human to manually verify arrays or database values.

For browser/UI cases that need login or a specific user state, agent mode must resolve a browser
test identity before blocking: reuse known safe test accounts, inspect local/test fixtures, create
a disposable fixture when the environment is clearly local/test and tooling is available, or ask
which test credentials/setup to use. Reusable test-only credentials may be saved to
`agent-context.md` only with explicit user permission; production or personal credentials,
cookies, sessions, and one-time codes are never persisted.

## Hermes-only skills

Not in lee-to's catalog, part of this department:

- **`aif-specify`** — the optional `spec` pre-stage of the pipeline (role `aif_specifier`):
  turns a raw brief into a testable spec under `.hermes-dev/specs/`; emits gate `spec`.
- **`aif-methodology`** — this reference library's parent skill: the department-wide picture,
  pipeline, gate contract, and no-stall laws.
- **`dev-handoff`** — routes dev work from conversational topics onto the `departments` board and
  subscribes the topic for progress.

## See Also

- [Development Workflow](workflow.md) — how workflow skills connect end-to-end
- [Quality Gates](quality-gates.md) — machine-readable gate contract
- [Reflex Loop](loop.md) — strict loop protocol for iterative quality gating
- [Plan Files](plan-files.md) — where workflow artifacts are stored
