---
name: aif
description: >-
  Entry skill of the AI Factory department — bootstrap a new application or set up
  AI context for an existing project. Analyzes or selects the tech stack, creates the
  app folder + `.hermes-dev/` scaffold + Hermes project, generates DESCRIPTION.md,
  AGENTS.md and base rules, wires skills, and delegates architecture to aif-architecture.
  Use when starting a new app/project, or when the user says "set up project", "new app",
  "bootstrap application", "configure AI context", "what skills do I need"
  (port of lee-to AI Factory /aif, adapted to Hermes).
tags:
  - aif
  - setup
  - bootstrap
  - dev-factory
  - kanban
---

# aif — Project Setup (department entry)

Set up agent context for a project: analyze the tech stack, bootstrap the workspace + Hermes project (for new apps), generate context artifacts, wire skills, and hand off to `aif-architecture`. This skill sets up context — it does **not** implement the project.

## Hermes context (how this differs from lee-to's original)

- Runs interactively (topic/CLI) or as a kanban worker on the `departments` board. Native Hermes kanban is the handoff layer — **no `HANDOFF_MODE`, no MCP handoff, no `.ai-factory/config.yaml`**. Paths are fixed by convention (below), so all config-file resolution/relocation logic from the original is gone.
- One app = one folder **`~/Work/apps/<slug>/`**. Dev-factory artifacts live under **`.hermes-dev/`**; project context files live at the **project root**: `DESCRIPTION.md`, `AGENTS.md`, and `ARCHITECTURE.md` (the latter is owned by `aif-architecture`).
- Skills live in **`~/.hermes/skills/<name>/`**. "Installing" a skill = adding its folder (SKILL.md + references) and verifying with `hermes skills list`. There is no `npx skills` marketplace and no python security scanner — third-party skills get a **manual security review** (see `references/third-party-skill-review.md`).
- **Autonomous mode:** kanban workers have no human at the keyboard. Do not use interactive questions — proceed on evidence, record every decision + rationale in the artifacts and the handoff. Block the kanban task (with the exact missing input) only when genuinely stuck — e.g. no app description at all — or when an action is irreversible/prod-affecting. Interactive (topic/CLI) use may ask.

## Step 0 — Load context

- Read **`.hermes-dev/skill-context/aif/SKILL.md`** — MANDATORY if it exists. Project rules accumulated by `aif-evolve`. Treat them as project-level overrides: on conflict, **skill-context wins** over this file; without conflict, apply both. They apply to ALL outputs of this run — DESCRIPTION.md, AGENTS.md, rules, skill wiring. The templates below are base structures: if a skill-context rule says "DESCRIPTION.md MUST include X" — augment the template. After generating each artifact, verify it against these rules and fix violations before finishing.
- Read the kanban task body + parent handoffs (`hermes kanban --board departments show <id>`) or the interactive brief.

## Mode detection

```
Task body / arguments:
├── Contains a project/app description? → Mode 2: New project with description
└── No description?
    └── Target folder has project files (package.json, composer.json,
        requirements.txt/pyproject.toml, go.mod, Cargo.toml, …)?
        ├── Yes → Mode 1: Analyze existing project
        └── No  → Mode 3: New project, no brief
                  (interactive: ask what we're building; autonomous: block —
                  "no app description in task body")
```

## Language resolution (simplified — no config.yaml)

Resolve once, keep fixed for the whole run:
1. Explicit language instruction in the task body/brief wins.
2. Existing project: match the language of `AGENTS.md` / `README.md` / existing docs.
3. Otherwise use the language of the brief itself.

The resolved artifact language governs the *content* of generated files (DESCRIPTION.md, AGENTS.md, rules); filenames stay unchanged, and technical terms (API, database, framework names, code) stay in English. Interactive replies follow the conversation language. Do not switch languages mid-run.

## Step 1 — New-application bootstrap (Modes 2/3)

For a **new application**, create a dedicated folder and Hermes project BEFORE generating artifacts, so every app lands in its own workspace:

1. Derive a slug from the app name — lowercase, hyphenated, ≤40 chars (e.g. "парсер цен X" → `parser-cen-x`).
2. Scaffold the standardized folder + `.hermes-dev/` and init git:
   ```
   mkdir -p ~/Work/apps/<slug>/.hermes-dev/{plans,specs,contracts,gates,rules,skill-context,research,fixes,qa,evolution,loop}
   git -C ~/Work/apps/<slug> init -q
   ```
3. Register the project (deterministic worktree + branch convention, board-bound):
   ```
   hermes project create "<App Name>" --slug <slug> --primary ~/Work/apps/<slug> --board departments
   ```
4. Anchor all downstream kanban tasks to the project so workers operate in its folder:
   `hermes kanban --board departments create "<task>" --assignee <aif_role> --project <slug> ...`

For an **existing app** (Mode 1), skip bootstrap: work in its folder, but ensure the `.hermes-dev/` scaffold above exists (create missing subdirectories only — never move or rewrite existing artifacts). Never scatter one app across two folders.

## Step 2 — Determine the stack

**Mode 1 — scan the project.** Read (if present): `package.json` (Node.js), `composer.json` (PHP/Laravel/Symfony), `requirements.txt`/`pyproject.toml` (Python), `go.mod` (Go), `Cargo.toml` (Rust), `docker-compose.yml` (services), `prisma/schema.prisma` (DB schema), and the directory structure (`src/`, `app/`, `api/`, …). Extract: language, framework, database, ORM, integrations, patterns.

**Modes 2/3 — select the stack.** Decide per category, with an explicit recommendation and WHY it fits this project type:
1. **Programming language** — performance, ecosystem, team experience
2. **Framework** — based on project type (not every project needs one)
3. **Database** — based on the data model (skip for e.g. a pure CLI tool)
4. **ORM / query builder** — based on language + database

Skip categories that don't apply. Interactive: present the recommendation and confirm. Autonomous: take the recommended choice, record the rationale in DESCRIPTION.md ("Architecture Notes") and in the handoff.

## Step 3 — Generate DESCRIPTION.md (project root)

Write `DESCRIPTION.md` at the project root, in the resolved artifact language:

```markdown
# [Project title]

## Overview
[Enhanced, clear description of the project]

## Core Features
- [Feature 1]
- [Feature 2]
- [Feature 3]

## Tech Stack
- **Language:** [choice]
- **Framework:** [choice]
- **Database:** [choice]
- **ORM:** [choice]
- **Integrations:** [Stripe, etc.]

## Architecture Notes
[High-level architecture decisions based on the stack + stack-choice rationale]

## Non-Functional Requirements
- Logging: configurable via LOG_LEVEL
- Error handling: structured error responses
- Security: [relevant security considerations]
```

For Mode 1, base the content on the scan: detected stack, identified patterns, architecture notes.

## Step 4 — Create `.hermes-dev/rules/base.md` from codebase evidence (Mode 1)

Analyze the codebase to detect: naming conventions (camelCase/snake_case/PascalCase), module boundaries (`src/core/`, `src/cli/`, `src/utils/`), error-handling patterns (try/catch, error codes), control-flow patterns (guard clauses, early returns, nesting), logging patterns (console.log, winston, pino), test patterns (jest, mocha, vitest).

Write `.hermes-dev/rules/base.md` with the detected conventions, in the resolved artifact language:

```markdown
# Project base rules

> Auto-detected conventions from codebase analysis. Edit as needed.

## Naming Conventions
- Files / Variables / Functions / Classes: [detected patterns]

## Module Structure
- [detected module boundaries]

## Error Handling
- [detected error handling pattern]

## Control Flow
- Prefer flat, readable control flow over deeply nested conditionals. Use guard
  clauses, early `return`/`continue`, small named helpers, or explicit
  classification logic. Handle edge cases early so the main path stays visible.

## Logging
- [detected logging pattern]
```

For new apps (Modes 2/3) there is no codebase to detect from — skip, or seed only the Control Flow section as the default.

## Step 5 — Wire skills (and MCP, only if essential)

**Recommend by detection:**

| Detection | Skills to wire | External integration |
|-----------|----------------|----------------------|
| Prisma/PostgreSQL | db-migrations-type skill | postgres access |
| MongoDB | mongo-patterns-type skill | — |
| Git repo (.git) | — | github (`gh` CLI is already available) |
| Stripe/payments | payment-flows-type skill | — |
| Domain-specific needs | generate via `aif-skill-generator` | — |

**Skill acquisition strategy** (replaces the skills.sh/npx installer):

```
For each recommended skill:
  1. Check: hermes skills list — already enabled? → skip (no duplicates)
  2. Available as an existing skill folder (lee-to port, local library)?
     → copy the folder into ~/.hermes/skills/<name>/
  3. SECURITY: third-party/external skill → manual review per
     references/third-party-skill-review.md
     - FAIL → delete the folder, record full threat details in the handoff, skip
     - WARN → record warnings; interactive: confirm with the user before keeping
  4. Not found anywhere → generate: load skill `aif-skill-generator` with the name
  5. Reference URLs / docs available? → Learn Mode: pass them to aif-skill-generator
     so it studies real documentation instead of generic patterns. Always prefer
     Learn Mode when reference material is available.
  6. Verify: hermes skills list shows the skill enabled
```

**MCP:** Hermes MCP servers are configured centrally in the Hermes config, not per-project — do not write per-runtime `mcpServers`/`servers` config files (the original's runtime format matrix does not apply here). If the project genuinely needs a new external integration, note it in the handoff for the operator (server name, purpose, required credentials in `.env`) rather than self-configuring.

## Step 6 — Generate AGENTS.md (project root)

`AGENTS.md` is the structural map for AI agents working in this repo. Scan the project first: directory tree (top 2–3 levels), key entry points (main files, configs, schemas), existing docs. Content in the resolved artifact language; the filename stays `AGENTS.md`.

```markdown
# AGENTS.md

> Maintenance note: keep this map factual and update it when the structure changes.

## Project Overview
[1-2 sentences from DESCRIPTION.md]

## Tech Stack
- **Language / Framework / Database / ORM:** [values]

## Project Structure
\`\`\`
[directory tree with inline comments explaining each directory]
\`\`\`

## Key Entry Points
| File | Purpose |
|------|---------|
| [main entry] | [description] |
| [config file] | [description] |
| [schema file] | [description] |

## Documentation
| Document | Path | Description |
|----------|------|-------------|
| README | README.md | [description] |
| [other docs if they exist] | | |

## AI Context Files
| File | Purpose |
|------|---------|
| AGENTS.md | This structural map |
| DESCRIPTION.md | Project spec: stack, features, NFRs |
| ARCHITECTURE.md | Architecture pattern, folder structure, dependency rules |
| .hermes-dev/ | Dev-factory artifacts: plans, specs, rules, skill-context, qa, research |

## Agent Rules
- Decompose compound shell commands instead of chaining them:
  - Incorrect: `git checkout <base-branch> && git pull`
  - Correct: first `git checkout <base-branch>`, then `git pull origin <base-branch>`
```

**Rules for AGENTS.md:** keep it factual — only what actually exists; the Documentation section is maintained by `aif-docs`; do NOT duplicate DESCRIPTION.md content — reference it.

## Step 7 — Generate the architecture document

After DESCRIPTION.md, AGENTS.md, rules, and skills are in place, load skill **`aif-architecture`**. It creates `ARCHITECTURE.md` at the project root with the architecture pattern, folder structure, dependency rules, and code examples tailored to the project. Do not write ARCHITECTURE.md yourself — that skill owns it.

## Step 8 — Wrap up & hand off

Report what was set up:

```
Setup complete
- Project spec:   DESCRIPTION.md
- Architecture:   ARCHITECTURE.md
- Project map:    AGENTS.md
- Base rules:     .hermes-dev/rules/base.md
- Hermes project: <slug> (~/Work/apps/<slug>, board departments)   [new apps]
- Skills wired:   [list]
Next steps:
- aif-roadmap  — strategic milestones (.hermes-dev/plans/ROADMAP.md)
- aif-plan     — break the first feature into an implementation plan
- aif-implement — execute the plan
```

For existing projects (Mode 1), also suggest: `aif-docs` (documentation), `aif-rules` (area rules), `aif-build-automation`, `aif-ci`, `aif-dockerize`. Interactive: offer these as options and run the selected ones sequentially. Autonomous: do not auto-run them — list them in the handoff and complete the kanban task on evidence (artifact paths + skills wired).

## Rules

1. **Search before generating** — don't reinvent skills that already exist in `~/.hermes/skills/`.
2. **No duplicates** — never install/wire what's already enabled.
3. **Security review every external skill** — both levels of `references/third-party-skill-review.md` must pass.
4. **Remind about env vars** — for integrations that need credentials (`.env`).
5. **Record decisions** — every autonomous stack/skill choice lands in DESCRIPTION.md and the handoff.

## Artifact ownership

- Primary: `DESCRIPTION.md`, setup-time `AGENTS.md`, `.hermes-dev/rules/base.md`, the `.hermes-dev/` scaffold, the Hermes project registration, and wired skills.
- Delegated: `ARCHITECTURE.md` → `aif-architecture`.
- Read-only here: roadmap, RULES.md, research, and plan artifacts.

## CRITICAL: Do NOT implement

This skill ONLY sets up context. **DO NOT** start writing project code, create `src/`/`app/` files, implement features, or set up structure beyond the scaffold + context artifacts above. Your job ends when the context artifacts, skills, and project registration are in place — planning starts with `aif-roadmap`/`aif-plan`, code starts with `aif-implement`.
