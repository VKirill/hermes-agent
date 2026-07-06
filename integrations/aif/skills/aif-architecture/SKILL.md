---
name: aif-architecture
description: >-
  Generate architecture guidelines for a project. Analyzes the tech stack from
  DESCRIPTION.md, recommends an architecture pattern via the decision matrix in
  references/architecture.md, and creates ARCHITECTURE.md at the project root.
  Use when defining project architecture, when the user asks "which architecture",
  "architecture guidelines", or right after aif project setup
  (port of lee-to AI Factory /aif-architecture, adapted to Hermes).
tags:
  - aif
  - architecture
  - design
  - dev-factory
---

# aif-architecture — Generate Architecture Guidelines

Produce `ARCHITECTURE.md` at the project root with architecture decisions tailored to the project: pattern, folder structure, dependency rules, and code examples in the project's own language/framework.

## Hermes context (how this differs from lee-to's original)

- Runs interactively or as a kanban worker on the `departments` board (typically invoked by the `aif` entry skill during setup). Native kanban is the handoff layer — **no `.ai-factory/config.yaml`**, paths are fixed: `DESCRIPTION.md` and `ARCHITECTURE.md` at the **project root** of the target app (`~/Work/apps/<slug>/`), dev artifacts under `.hermes-dev/`.
- **Autonomous mode:** no interactive questions. Where the original asks the user (variant choice, alignment strategy), decide from evidence using the defaults defined below and record the decision + rationale in ARCHITECTURE.md's "Decision Rationale". Block only when there is no project context at all (no DESCRIPTION.md, no codebase, no brief in the task body).

## Step 0 — Load project context

**Read `DESCRIPTION.md`** (project root) if it exists, to understand:
- Tech stack (language, framework, database, ORM)
- Project size and complexity
- Core features and non-functional requirements

**If `DESCRIPTION.md` does not exist** — standalone usage is allowed:
- Interactive: ask for the essentials (what is being built, stack, team size, expected scale) or suggest running `aif` first.
- Autonomous: derive them from the kanban task body + a quick codebase scan; if neither yields enough, **block** with "no project description — run aif setup first or provide stack/scale in the task body".

**Read `.hermes-dev/skill-context/aif-architecture/SKILL.md`** — MANDATORY if it exists. Project rules accumulated by `aif-evolve`; treat as project-level overrides: on conflict **skill-context wins** over this file, otherwise apply both. They apply to ALL outputs — including the ARCHITECTURE.md template below (it is a base structure; if a rule says "the architecture doc MUST include X" — augment it). After generating, verify the output against these rules and fix violations before finishing.

Also read the kanban task body + parent handoffs for an explicitly requested pattern.

## Step 1 — Resolve or recommend the architecture

**If the task/brief specifies a pattern**, map it:

- **Direct mapping** (no suffix needed):
  - `layers` → Layered Architecture
  - `microservices` → Microservices
  - `structured` → Structured Modules (variant undetermined — see below)
  - `explicit` → Explicit Architecture (variant undetermined — see below)
- **Legacy aliases** (deprecated, still accepted):
  - `clean` → Explicit Architecture; `ddd` → Explicit Architecture
  - `monolith` → Structured Modules; `vertical` → Explicit Architecture (Vertical Slice By Entity)
- **With suffix** (variant determined):
  - `structured-layers` → Structured Modules (Technical Layer)
  - `structured-vertical` → Structured Modules (Vertical Slices By Entity)
  - `explicit-layers` → Explicit Architecture (Technical Layer)
  - `explicit-vertical` → Explicit Architecture (Vertical Slice By Entity)
  - `explicit-flat` → Explicit Architecture (Flat Vertical Slice - Simplified)
- **Without suffix** — the variant must still be chosen:
  - Interactive: ask. `structured` → "1. Technical Layer (simpler) or 2. Vertical Slices by Entity (better for large modules)?" `explicit` → "1. Technical Layer, 2. Vertical Slice By Entity, or 3. Flat Vertical Slice (Simplified)?" Wait for the answer.
  - Autonomous: pick by module/context size and feature independence (guidance in `references/architecture.md` — small modules/max cohesion → flat/technical-layer variants; many independent features → vertical slices) and record the choice + reason.

Use the resolved pattern directly and skip the recommendation; proceed to Step 1.5.

**If no pattern is requested:**
- Evaluate the project against the decision matrix in `references/architecture.md` — team size, domain complexity, scale requirements, feature independence, tech stack.
- Candidate patterns: Structured Modules (Technical Layer | Vertical Slices By Entity), Explicit Architecture (Technical Layer | Vertical Slice By Entity | Flat Vertical Slice - Simplified), Microservices, Layered Architecture.
- Interactive: present the recommendation with 1–2 project-specific reasons plus 2–3 alternatives, and let the user choose.
- Autonomous: take the matrix-backed recommendation and record the reasoning.

**CRITICAL:** You MUST read `references/architecture.md` before generating ARCHITECTURE.md — it is the source of correct terminology, folder structures, and dependency directions. Never generate the artifact from memory.

## Step 1.5 — Codebase alignment check

**Before generating**, compare the chosen pattern's ideal folder structure (from `references/architecture.md`) against the actual codebase.

- Empty project or mostly matching → proceed to Step 2.
- **Significant discrepancies** → do NOT silently merge the ideal architecture with the messy reality. Two strategies:
  1. **Adapt** — document guidelines fitted to the existing structure (document reality).
  2. **Strict** — generate the pure architecture guidelines (implies future refactoring to match).

  Interactive: list 1–2 major differences and ask which strategy to use; wait for the decision.
  Autonomous: default to **Adapt (1)** unless the task body explicitly requests a strict/target architecture or a refactor; record which strategy was applied and the differences observed.

## Step 2 — Generate ARCHITECTURE.md (project root)

Create `ARCHITECTURE.md` at the project root with this structure, **adapted to the project's tech stack** and written in the project's artifact language:

```markdown
# Architecture: [Pattern Name]

## Overview
[1-2 paragraphs: what this architecture is and why it was chosen for THIS project]

## Decision Rationale
- **Project type:** [from DESCRIPTION.md]
- **Tech stack:** [language, framework]
- **Key factor:** [primary reason for this choice]
[+ autonomous-mode decisions made in Steps 1/1.5, with reasons]

## Folder Structure
\`\`\`
[folder structure adapted to the project's tech stack]
[use actual framework conventions — e.g. Next.js app/ dir, Laravel app/ dir, Go cmd/ dir]
\`\`\`

## Dependency Rules
[What depends on what. Inner vs outer layers. Module boundaries.]
- ✅ [allowed dependency direction]
- ❌ [forbidden dependency direction]

## Layer/Module Communication
- [pattern 1]
- [pattern 2]

## Key Principles
1. [Principle 1 — adapted to this project]
2. [Principle 2]
3. [Principle 3]

[If Strict (Step 1.5, option 2) was chosen, add:]
## Legacy vs New Code Policy
- **New Features:** All new code MUST strictly follow the architecture defined here.
- **Legacy Code Modification:** Do NOT automatically refactor unrelated legacy code to fit.
  Touch legacy code only for bug fixes, explicit refactoring tasks, or adapting it for
  consumption by new features.
- **Interoperability:** When new code must call legacy code, isolate the interaction with
  adapters/interfaces/facades so legacy patterns do not pollute the new architecture.

[If Adapt (Step 1.5, option 1) was chosen, add the lighter version:]
## Code Organization Note
- **New Features:** New code should follow this document where practical.
- **Existing Code:** Documented as-is. When modifying, prefer these conventions, but do not
  force rewrites of unrelated code.
- **Interoperability:** Prefer clean interfaces between new and existing code; do not
  refactor purely for structural alignment.

## Code Examples
### [Example 1 title]
\`\`\`[language]
[code example in the project's language/framework]
\`\`\`
### [Example 2 title]
\`\`\`[language]
[code example showing a dependency rule]
\`\`\`

## Anti-Patterns
- ❌ [What NOT to do in this architecture]
- ❌ [Common mistake to avoid]
```

**Rules for generation:**
- Adapt ALL examples to the project's language and framework (no TypeScript examples for a Go project).
- Use the project's actual conventions (import paths, naming, etc.).
- Keep it practical — rules that affect day-to-day development.
- Base the generated folder structure on the Step 1.5 strategy (adapted to reality OR strict). Never merge them silently.

## Step 3 — Update DESCRIPTION.md

If `DESCRIPTION.md` exists at the project root, add or update an architecture-pointer section (in the artifact language):

```markdown
## Architecture
See ARCHITECTURE.md for detailed architecture guidelines.
Pattern: [chosen pattern name]
```

## Step 4 — Update AGENTS.md

If `AGENTS.md` exists at the project root, add `ARCHITECTURE.md` to its "AI Context Files" table (only if not already present):

```markdown
| ARCHITECTURE.md | Architecture pattern, folder structure, dependency rules |
```

## Step 5 — Confirm & hand off

Report: the chosen pattern, the file path (`ARCHITECTURE.md` at project root), 2–3 key rules, and the note that downstream workflow skills (`aif-plan`, `aif-implement`) follow these guidelines for file placement and module boundaries. As a kanban worker, complete the task with this structured handoff; interactively, present the same summary.

## Artifact ownership

- Primary: `ARCHITECTURE.md` at the project root of the target app.
- Allowed companion updates: the architecture pointer in `DESCRIPTION.md`, the architecture row in `AGENTS.md`.
- Read-only: roadmap, rules, research, and plan artifacts — unless explicitly tasked otherwise.
