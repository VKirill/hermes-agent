---
name: aif-reference
description: >-
  Create and maintain structured knowledge references from URLs, documents, or local
  files for use by AI agents. Fetch, process, and store references in .hermes-dev/reference/
  with an INDEX.md, so aif-plan, aif-implement, aif-explore and aif-grounded can reuse
  them. Use when the user says "create reference", "save these docs", "make a reference
  from", "update reference", "reference list/show/delete"
  (port of lee-to AI Factory /aif-reference, adapted to Hermes).
tags:
  - aif
  - knowledge-management
  - reference
  - dev-factory
---

# aif-reference — Reference creator

Create structured knowledge references from external sources and store them in `.hermes-dev/reference/` so other AIF skills can reuse them later.

## Hermes context

- References live at **`.hermes-dev/reference/`** in the app workspace; paths are fixed — no `.ai-factory/config.yaml`, no language-resolution machinery. Write references in English by default; match the existing reference set's language if one is established.
- **Autonomy:** interactive sessions may ask clarifying questions (interactive mode below). As a kanban worker, derive sources and scope from the task body; if sources are missing or unreachable, `kanban_block` with the exact missing input. Deletions are destructive — a worker deletes only when the task explicitly orders it; interactive use confirms first.

## When to use

- AI needs documentation it was not trained on or may know only partially
- You want grounded answers based on specific docs, specs, or internal files
- You want reusable domain context for `/aif-plan`, `/aif-implement`, `/aif-explore`, or `/aif-grounded`
- You want a durable knowledge artifact instead of one-off conversation context

## Argument detection

```text
Check the request text:
- Contains "--update"        -> Update Mode: refresh existing reference
- Contains URLs (http/https) -> URL Mode: fetch and process web sources
- Contains file paths        -> File Mode: process local documents
- "list"                     -> List existing references
- "show <name>"              -> Show reference content
- "delete <name>"            -> Delete a reference (with confirmation / explicit order)
- Empty                      -> Interactive mode (interactive sessions only)
```

## Step 0 — Load skill context

**Read `.hermes-dev/skill-context/aif-reference/SKILL.md` — MANDATORY if it exists.** Project-specific rules accumulated by `/aif-evolve` from patches, codebase conventions, and tech-stack analysis.

How to apply: treat them as **project-level overrides**; on conflict the skill-context rule wins; no conflict → apply both. **CRITICAL:** they apply to ALL outputs of this skill, including the generated reference files ("references MUST include X" → comply). **Enforcement:** after generating any output artifact, verify it against all skill-context rules; fix violations before finishing.

## Workflow

### Step 0.1 — Setup

Ensure the references directory exists: `mkdir -p .hermes-dev/reference`. Check existing references to avoid duplicates: `ls .hermes-dev/reference`.

If `--name <ref-name>` is provided, use it as the reference name. If `--update` is provided, find and update the existing reference instead of creating a new one.

### Step 1 — Collect sources

**For URLs** — for each URL:
1. Fetch the page (WebFetch or equivalent) and extract:
   - main topic and purpose
   - key concepts, terms, and definitions
   - code examples and patterns
   - API methods, parameters, return types, and signatures
   - configuration options with defaults
   - best practices and recommendations
   - error handling and edge cases
   - version information and compatibility notes
   - links to critical sub-pages
2. If critical sub-pages are referenced, fetch them too (up to 8 extra pages per source URL).
3. If obvious gaps remain, run 1-2 targeted web searches to fill them.

**For local files:**
1. Read each file with `Read`
2. If the file references other local files, read those too (up to 5 levels of includes)
3. Detect the format (markdown, HTML, JSON, YAML, plain text) and extract accordingly

**For interactive mode** — ask the user:
1. What topic or technology should this reference cover?
2. Do they have URLs or local files, or should you search?
3. What aspects matter most for their use case?

(Kanban worker: never enter interactive mode — block with "sources not specified" instead.)

### Step 2 — Synthesize the reference

Transform collected material into a structured reference document.

**Reference file format:**

```markdown
# <Topic> Reference

> Source: <list of source URLs or file paths>
> Created: YYYY-MM-DD
> Updated: YYYY-MM-DD

## Overview

<1-3 paragraph summary>

## Core Concepts

<Concept 1>: <clear explanation>
<Concept 2>: <clear explanation>

## API / Interface

<Only if applicable. Preserve exact signatures and types from source docs.>

## Usage Patterns

<Practical code examples organized by use case.>

## Configuration

<Options, defaults, valid values. Table format preferred.>

## Best Practices

<Numbered list with reasoning>

## Common Pitfalls

<What goes wrong and how to avoid it>

## Version Notes

<Only if relevant. Breaking changes, migration notes, deprecations.>
```

**Quality rules:**
- **No hallucination** — include only what was actually found
- **Preserve code verbatim** — docs examples must stay exact
- **Actionable over academic** — optimize for useful lookup
- **Dense** — maximize useful information per line
- **Complete signatures** — APIs need full parameters, types, and returns
- **Source attribution** — always include source URLs or paths

### Step 3 — Name and save

Naming convention:
- Derive from topic: `react-hooks.md`, `fastapi-endpoints.md`, `docker-compose.md`
- Use lowercase, hyphens, `.md`
- If `--name` was provided, use that (add `.md` if missing)
- Avoid generic names like `reference.md`

**Save to:** `.hermes-dev/reference/<name>.md`

### Step 4 — Register in index

Check if `.hermes-dev/reference/INDEX.md` exists. Create or update it (keep filenames, links, URLs, and dates unchanged):

```markdown
# References Index

Available knowledge references for AI agents.

| Reference | Topic | Sources | Updated |
|-----------|-------|---------|---------|
| [react-hooks](react-hooks.md) | React Hooks API and patterns | react.dev | 2026-03-20 |
| [docker-compose](docker-compose.md) | Docker Compose configuration | docs.docker.com | 2026-03-20 |
```

### Step 5 — Report

Report (to the user, or in the kanban handoff): reference name and path, size (line count), sections included, source URLs or file paths used, and how to use it in later AIF workflows.

## Update mode (`--update`)

1. Find the existing reference by `--name` or matching sources
2. Re-fetch the sources listed in the header
3. Compare new material with existing content and update only changed sections
4. Preserve `Created:`, update `Updated:`
5. Report what changed

## List / Show / Delete

- **`list`** — read and display `.hermes-dev/reference/INDEX.md` or list files in the directory
- **`show <name>`** — read and display the reference content (`.md` is optional)
- **`delete <name>`** — interactive: ask for confirmation; kanban worker: only on explicit order in the task body. Then delete the file and update `INDEX.md`.

## Integration with other skills

References in `.hermes-dev/reference/` are available to all AIF skills:
- `/aif-plan` and `/aif-implement` can read them for domain context
- `/aif-grounded` can use them as evidence sources
- `/aif-explore` can reference them during research

To make a skill aware of a specific reference, mention it in `.hermes-dev/RULES.md`:

```markdown
## References
- For <topic> details, see `.hermes-dev/reference/<name>.md`
```

## Artifact ownership

- **Primary ownership:** `.hermes-dev/reference/`
- **Shared ownership:** `.hermes-dev/reference/INDEX.md`
- **Read-only:** all other `.hermes-dev/` files and project context files (DESCRIPTION.md, ARCHITECTURE.md)

## Guardrails

- **Max reference size:** aim for under 1000 lines per reference. If larger, split into multiple files inside a subdirectory of `.hermes-dev/reference/` with its own `INDEX.md`
- **No duplication:** check existing references before creating a new one
- **No stale data:** always include sources so the reference can be refreshed
- **No opinions:** references should reflect sources, not personal preferences
- **Respect access:** if a URL requires authentication or fails to load, report that instead of guessing
