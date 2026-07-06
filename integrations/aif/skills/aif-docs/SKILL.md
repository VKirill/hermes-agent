---
name: aif-docs
description: >-
  Generate, audit, and maintain project documentation: a lean landing-page README plus
  self-contained docs pages split by topic under docs/, with navigation, review
  checklists, and an optional static HTML site. Use when the user says "create docs",
  "write documentation", "update docs", "generate readme", or "document project"
  (port of lee-to AI Factory /aif-docs, adapted to Hermes).
tags:
  - aif
  - documentation
  - dev-factory
---

# aif-docs — Project Documentation Generator

Generate, maintain, and improve project documentation following a landing-page README + detailed docs-directory structure.

## Hermes context (how this differs from lee-to's original)

- Runs interactively or as a kanban worker on the `departments` board. **No `.ai-factory/config.yaml`** — paths are fixed: `README.md` at the project root of the target app (`~/Work/apps/<slug>/`); detailed docs under **`docs/`** at the project root (if the project already keeps detailed docs elsewhere — `documentation/`, `handbook/`, `site/docs/` — follow that existing convention and record which directory you used); `DESCRIPTION.md` and `ARCHITECTURE.md` at the project root; dev artifacts under `.hermes-dev/`.
- The `docs-auditor` sidecar (spawned from `aif-implement` coordination flows) may recommend running this skill after code changes; its findings arrive in the task body.
- **Autonomous mode:** no interactive questions. Where the original asks (consolidation plan, topic list, applying fixes), proceed on evidence with the safe default and report the decisions in the handoff. **Never delete original files autonomously** — moves/merges are applied, originals are kept and listed for cleanup. Interactive use keeps the original questions. Below, each decision point states both behaviors.

## Core principles

1. **README is a landing page, not a manual.** ~80–120 lines. First impression, install, quick example, links to details.
2. **Details go to the docs directory** (default `docs/`). Each file is self-contained — one topic, one page. A reader should get the full picture on a topic from a single file.
3. **No duplication.** If information lives in the docs directory, README links to it — never repeats it. Exception: the installation command may appear in both (users expect it in README).
4. **Navigation.** Every docs page has a header line with prev/next links following the README Documentation-table order: `[← Previous Page](prev.md) · [Back to README](../README.md) · [Next Page →](next.md)`. First page has no prev link; last page has no next link. Every page ends with a "See Also" section linking 2–3 related pages.
5. **Cross-links use relative paths.** From README: `docs/workflow.md`. Between pages in the same directory: `workflow.md`.
6. **Scannable.** Tables, bullet lists, code blocks. No long paragraphs — users scan, they don't read.

## Workflow

### Step 0 — Load project context

Read if present:
- `DESCRIPTION.md` (project root) — tech stack, purpose, key features, conventions
- `ARCHITECTURE.md` (project root) — structure and boundaries the docs must align with
- **`.hermes-dev/skill-context/aif-docs/SKILL.md` — MANDATORY if it exists.** Project rules accumulated by `aif-evolve`; treat as project-level overrides: on conflict **skill-context wins** over this file, otherwise apply both. They apply to ALL outputs — README.md, docs pages, and their templates (base structures: if a rule says "docs MUST include X" or "README MUST have section Y", augment the templates). Verify every generated/modified file against these rules before presenting; fix violations first.
- The kanban task body + parent handoffs.

**Explore the codebase:**
- `package.json`, `composer.json`, `requirements.txt`, `go.mod`, `Cargo.toml`, etc.
- `src/` structure for architecture
- Existing docs, comments, API endpoints, CLI commands
- Existing `README.md` and docs directory

**Scan for scattered markdown files in the project root** (`Glob` for root `*.md`; exclude `node_modules/`, `.hermes-dev/`, vendor and agent dirs): `CHANGELOG.md, CONTRIBUTING.md, ARCHITECTURE.md, DEPLOYMENT.md, SECURITY.md, API.md, SETUP.md, DEVELOPMENT.md, TESTING.md, …` Record each file, its size, and a one-line content summary — used in Step 1.1.

**Note:** the root `DESCRIPTION.md`, `AGENTS.md`, and `ARCHITECTURE.md` are AI-context files owned by other aif skills — they are NOT "scattered docs" and never move.

### Step 0.1 — Parse flags

```
--web (or the task asks for an HTML/static site) → also generate the HTML version
```

### Step 1 — Determine current state

```
State A: No README.md                     → Full generation (README + docs dir)
State B: README.md exists, no docs dir    → Analyze README, propose split into docs dir
State C: README.md + docs dir both exist  → Depends on flags (below)
```

**State C with `--web`** — choose the scope:
1. Generate HTML only — build the site from current docs as-is
2. Audit & improve first — fix issues, then generate HTML
3. Audit only — report issues, no HTML

Interactive: ask which. Autonomous: default to **2 (audit & improve, then HTML)**.
- HTML only → skip Steps 1.1, 2, 4 — go straight to Step 3, then done.
- Audit & improve first → Step 1.1 → Step 2 (State C) → Step 3 → Step 4 → Step 4.1.
- Audit only → Step 1.1 → Step 2 (State C) → Step 4 → Step 4.1 (skip Step 3).

**State C without `--web`** → run Step 2 (State C) as usual.

### Step 1.1 — Consolidate scattered markdown files

If scattered root `*.md` files were found in Step 0, propose moving them into the docs directory.

| Root file | Target in docs dir | Merge or move? |
|-----------|--------------------|----------------|
| `CONTRIBUTING.md` | `docs/contributing.md` | Move |
| `ARCHITECTURE.md`* | `docs/architecture.md` | Move (*only a docs-style architecture overview; the aif-owned AI-context `ARCHITECTURE.md` stays at root) |
| `DEPLOYMENT.md` | `docs/deployment.md` | Move |
| `SETUP.md` | `docs/getting-started.md` | Merge (append to existing) |
| `DEVELOPMENT.md` | `docs/getting-started.md` or `docs/contributing.md` | Merge |
| `API.md` | `docs/api.md` | Move |
| `TESTING.md` | `docs/testing.md` | Move |
| `SECURITY.md` | `docs/security.md` | Move |

**Files that stay in root** (standard convention): `README.md` (always), `CHANGELOG.md`, `LICENSE`/`LICENSE.md`, `CODE_OF_CONDUCT.md` — plus the aif context files `DESCRIPTION.md`, `AGENTS.md`, `ARCHITECTURE.md`.

Present the plan (found files with sizes/summaries + suggested move/merge actions). Interactive: ask (apply all | pick individually | skip) and apply only what's approved — **never force-move**. Autonomous: apply the suggested moves/merges and record every action in the handoff.

**When moving/merging:**
1. Create the target docs file with the prev/next navigation header (Documentation-table order) and a "See Also" footer.
2. When merging into an existing page — append under a new section header; do not duplicate content already there.
3. **Do NOT delete originals yet** — keep them until the Step 4 review confirms everything is in place.
4. Add the new page to README's Documentation table (path relative to README).
5. Update links in other files that pointed to the old root-level file.
6. Record which files were moved/merged — the list feeds Step 4.1.

### Step 2 (State A) — Generate from scratch

#### 2.1 Identify documentation topics

```
Always include:
- getting-started.md    (installation, setup, quick start)

Include if relevant:
- architecture.md       (clear architecture: services, modules, layers)
- api.md                (project exposes API endpoints)
- configuration.md      (config files, env vars, feature flags)
- deployment.md         (Dockerfile, CI/CD, deploy scripts exist)
- contributing.md       (open-source or team project)
- security.md           (auth, permissions, security patterns)
- testing.md            (test suite exists)
- cli.md                (CLI commands)
```

Interactive: present the suggested page list and ask (generate all | pick individually | add more topics), confirm the final list. Autonomous: generate all relevant pages per the detection above (cap at 6–8 pages — an inviting docs set, not an overwhelming one).

#### 2.2 Generate README.md (~80–120 lines)

```markdown
# Project Name

> One-line tagline describing the project.

Brief 2-3 sentence description of what this project does and why it exists.

## Quick Start

\`\`\`bash
# Installation steps (1-3 commands)
\`\`\`

## Key Features

- **Feature 1** — brief description
- **Feature 2** — brief description
- **Feature 3** — brief description

## Example

\`\`\`
# A real usage example — this is where users decide "I want this"
\`\`\`

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](docs/getting-started.md) | Installation, setup, first steps |
| [Architecture](docs/architecture.md) | Project structure and patterns |
| [API Reference](docs/api.md) | Endpoints, request/response formats |
| [Configuration](docs/configuration.md) | Environment variables, config files |

## License

MIT (or whatever the project actually uses)
```

**Key README rules:** logo/badge line at top (if any); tagline as blockquote; Quick Start with real install commands (detected from the package manager); 3–6 scannable Key Features; a real example with the "wow factor"; Documentation table linking to the docs dir; license at the bottom; **NO long descriptions, NO full API reference, NO configuration details**.

#### 2.3 Generate the docs pages

For each approved topic:

```markdown
[← Previous Topic](previous-topic.md) · [Back to README](../README.md) · [Next Topic →](next-topic.md)

# Topic Title

Content organized by subtopic with headers, code examples, and tables.
Keep each section self-contained.

## See Also

- [Related Topic 1](related-topic.md) — brief description
- [Related Topic 2](other-topic.md) — brief description
```

**Navigation order** follows the README Documentation table top-to-bottom; the first page omits "← Previous", the last omits "Next →". Example for the default `docs/` layout:

```
getting-started.md:  [Back to README](../README.md) · [Architecture →](architecture.md)
architecture.md:     [← Getting Started](getting-started.md) · [Back to README](../README.md) · [API Reference →](api.md)
api.md:              [← Architecture](architecture.md) · [Back to README](../README.md) · [Configuration →](configuration.md)
configuration.md:    [← API Reference](api.md) · [Back to README](../README.md)
```

**Content guidelines per topic:**
- **getting-started.md:** prerequisites (runtime versions, tools) → step-by-step install → first run / quick start → verify it works (expected output) → next-steps links
- **architecture.md:** high-level overview (diagram if useful) → directory structure with explanations → key patterns (naming, imports, error handling) → data flow
- **api.md:** base URL/configuration → authentication → endpoints grouped by resource → request/response examples → error codes
- **configuration.md:** all env vars with descriptions and defaults → config files and purpose → feature flags
- **deployment.md:** build steps → environment setup → CI/CD pipeline description → monitoring/health checks

### Step 2 (State B) — Split an existing README into the docs dir

When README.md exists, is long (150+ lines), and there is no docs directory yet.

#### 2.1 Analyze the README structure

**Stays in README:** title, tagline, badges; "Why?" / key-features bullets; quick install (1–3 commands); brief example; Documentation links table; external links, license.

**Moves to the docs dir:** detailed setup → `getting-started.md`; architecture/structure → `architecture.md`; full API reference → `api.md`; configuration details → `configuration.md`; contributing guidelines → `contributing.md`; any single-topic section longer than ~30 lines.

#### 2.2 Propose the split

Show the plan: resulting README outline (~100 lines) + the section→docs-page mapping. Interactive: confirm before proceeding. Autonomous: proceed with the plan and record the mapping in the handoff.

#### 2.3 Execute

1. Create the docs directory.
2. Create each page from the README content + prev/next navigation header + "See Also" footer.
3. Rewrite README as a landing page with the Documentation table.
4. **Verify no content was lost** — every section of the old README must exist somewhere.

### Step 2 (State C) — Improve existing docs

#### 2.1 Audit current documentation

Check for:
- **README length** — still a landing page (<150 lines)?
- **Missing topics** — undocumented aspects of the project?
- **Stale content** — references to files/APIs that no longer exist?
- **Navigation** — do all pages have prev/next headers and "See Also"?
- **Broken links** — do all internal links point to existing files/anchors?
- **Consistency** — same formatting style across all pages?
- **Standards compliance** — do existing docs match the current skill standards? (2.1.1)

#### 2.1.1 Standards compliance check

Compare existing docs against the Core Principles for gaps (missing navigation, missing "See Also", stale formats). Full compliance table + auto-fix rules → `references/REVIEW-CHECKLISTS.md` (Standards Compliance section). Include found gaps in the audit report alongside content issues, as regular improvements.

#### 2.2 Propose improvements

Present an audit report — per finding: ✅ ok / ⚠️ improvement / ❌ broken — plus a numbered fix list, e.g.:

```
✅ README is lean (105 lines)
⚠️  docs pages are missing prev/next navigation — will add
⚠️  docs/api.md is missing — project has 12 API endpoints
❌ docs/getting-started.md links to setup.md which doesn't exist

Proposed fixes: 1. add navigation to all pages 2. create docs/api.md 3. fix the broken link
```

Interactive: ask before applying. Autonomous: apply the fixes and include the report + applied-fix list in the handoff.

### Step 3 — Generate the HTML version (web mode)

1. `mkdir -p docs-html`
2. For each markdown file (README.md + docs pages) generate an HTML page from the template at `templates/html-template.html` in this skill folder, filling `{page_title}`, `{project_name}`, `{nav_links}`, `{content}`.
3. Convert markdown → HTML elements; rewrite `.md` links to `.html`; generate the nav bar; write to `docs-html/`. File mapping: `README.md` → `index.html`, `docs/*.md` → `*.html`.
4. Show the tree of generated files and the `open docs-html/index.html` hint.
5. Add `docs-html/` to `.gitignore` if not already ignored.

### Step 4 — Documentation review

**MANDATORY after any content change** (generation, split, improvement, consolidation). Skip only when "HTML only" was chosen — nothing was modified.

Read every generated/modified file and evaluate it against **both** checklists in `references/REVIEW-CHECKLISTS.md` — **Technical Accuracy** and **Readability & Completeness** ("new user eyes"). Fix issues found BEFORE presenting the result. Display the results as a compact table with ✅/❌/⚠️ per item (format at the end of the reference file).

### Step 4.1 — Clean up moved files

**Only if files were moved/merged from root during Step 1.1.** After the review confirms all content is correctly placed:

- Interactive: list the incorporated originals and ask (delete all | pick individually | keep them). When deleting: (1) verify one more time that the target docs file contains all original content, (2) delete the root file, (3) run `git status` so the user sees what was removed (restorable via git).
- Autonomous: **do not delete.** Keep the originals and list them in the handoff as "incorporated into docs/, safe to delete" — deletion happens only on explicit request or interactive approval.

### Step 5 — Update AGENTS.md

After any documentation change, update the `## Documentation` section in `AGENTS.md` (project root) to reflect the current doc set:

```markdown
## Documentation
| Document | Path | Description |
|----------|------|-------------|
| README | README.md | Project landing page |
| Getting Started | docs/getting-started.md | Installation, setup, first steps |
| Architecture | docs/architecture.md | Project structure and patterns |
| API Reference | docs/api.md | Endpoints, request/response formats |
```

**Rules:** README first, then the docs pages in the same order as the README Documentation table; reflect moves/merges from Step 1.1; add new pages, remove deleted ones; descriptions under 10 words; if `AGENTS.md` doesn't exist, skip silently.

## Handoff

As a kanban worker, complete the task with a structured handoff: files created/modified, consolidation actions (moved/merged + originals kept), review-checklist results, and any items needing a human decision (e.g. deleting originals). Interactively, present the same summary.

## Artifact ownership

- Primary: `README.md`, the docs directory (`docs/*` by default), and the Documentation section of `AGENTS.md`.
- Read-only context: `DESCRIPTION.md`, `ARCHITECTURE.md`, roadmap/rules/research artifacts — unless the user explicitly asks for broader edits.

## Important rules

1. **Show the plan before changing existing documentation** — interactive: get approval; autonomous: record the plan + actions in the handoff.
2. **Never delete content** without moving it somewhere else first.
3. **Detect real project info** — don't invent features; read package.json/config files.
4. **Use the project's language** — if the project README is in Russian, write docs in Russian.
5. **Preserve existing badges/logos** — don't drop them during restructuring.
6. **`.gitignore`** — when generating HTML, ensure `docs-html/` is ignored.
7. **Ownership boundary** — this skill owns documentation artifacts (README, docs dir, AGENTS.md Documentation section), not the roadmap, RULES.md, or research artifacts.
