---
name: aif-rules
description: >-
  Add project-specific rules and conventions to .hermes-dev/RULES.md (axioms) or
  .hermes-dev/rules/<area>.md (area rules). Each invocation appends new rules; rules are
  automatically loaded by aif-implement, aif-plan and the gate skills before execution.
  Use when the user says "add rule", "remember this", "convention", "always do X", or when
  a review/retro produces a durable project convention
  (port of lee-to AI Factory /aif-rules, adapted to Hermes).
tags:
  - aif
  - rules
  - conventions
  - dev-factory
  - knowledge-management
---

# aif-rules — Project rules & conventions

Add short, actionable rules and conventions for the current project. Rules are saved to `.hermes-dev/RULES.md` (or `.hermes-dev/rules/<area>.md` for area rules) and automatically loaded by `aif-implement` and the other aif-* skills before task execution.

## Hermes context

- Artifacts live under **`.hermes-dev/`** in the app workspace (`~/Work/apps/<slug>/`). Paths are **fixed** — there is no `.ai-factory/config.yaml` and no path/language resolution step. Rules artifacts are written in English by default; if an existing RULES.md is already written in another language, match it.
- **Autonomy:** in interactive sessions (topic/CLI) you may ask the user for the rule text. As a kanban worker you must NOT ask — derive the rule from the kanban task body / handoff; if no rule text can be derived, `kanban_block` with the exact missing input.

## Rules hierarchy

Three levels, more specific wins: `.hermes-dev/rules/<area>.md` > `.hermes-dev/rules/base.md` > `.hermes-dev/RULES.md`.

1. **`.hermes-dev/RULES.md`** — axioms (universal project rules). Managed by this skill. Short, flat list of hard requirements. Loaded by all aif-* skills.
2. **`.hermes-dev/rules/base.md`** — project-specific base conventions. Created by the `/aif` setup skill from codebase analysis: naming conventions, module boundaries, error handling patterns.
3. **`.hermes-dev/rules/<area>.md`** — area-specific conventions (this skill, Mode C). Discovered by filename inside `.hermes-dev/rules/` — no registry needed.

## Step 0 — Load skill context

**Read `.hermes-dev/skill-context/aif-rules/SKILL.md` — MANDATORY if it exists.** It contains project-specific rules accumulated by `/aif-evolve` from patches, codebase conventions, and tech-stack analysis.

How to apply skill-context rules:
- Treat them as **project-level overrides** for this skill's general instructions; on conflict, **skill-context wins** (more specific context takes priority — same principle as nested CLAUDE.md files). No conflict → apply both.
- Do NOT ignore them even if they seem to contradict this skill's defaults — they exist because the project's experience proved the default insufficient.
- **CRITICAL:** they apply to ALL outputs of this skill, including the RULES.md format and rule formulation ("rules MUST follow format X", "RULES.md MUST include section Y" → comply).
- **Enforcement:** after generating any output artifact, verify it against all skill-context rules; fix violations before finishing.

## Step 1 — Determine mode

```text
Check the request text:
- Starts with "area:" or "area "? -> Mode C: Area rules
- Has rule text?                  -> Mode A: Direct add
- No rule text?                   -> Mode B: Interactive (interactive sessions only)
```

### Mode A: Direct add

Rule text was provided (e.g. "Always use DTO classes instead of arrays"). Skip to Step 2 with the provided text as the rule.

### Mode B: Interactive

No rule text provided. Interactive session → ask: "What rule or convention would you like to add?" with examples:
- Always use DTO classes instead of arrays for data transfer
- Routes must use kebab-case
- All database queries go through repository classes
- Never use raw SQL, always use the query builder
- Log every external API call with request/response

Kanban worker → no questions: extract the rule from the task body; nothing extractable → `kanban_block` with "rule text missing".

### Mode C: Area rules

Request like `area:api` or `area frontend`:

1. **Parse the area name** (e.g. `api`, `frontend`, `backend`, `database`).
2. **Resolve the area file path:** `.hermes-dev/rules/<area>.md`.
3. **Check if the file exists** (Glob).
4. **If it does NOT exist** → create it with header:

   ```markdown
   # <Area> Rules

   > Area-specific conventions for <area>. Loaded after rules/base.md.

   ## Rules

   - [first rule]
   ```

5. **If it exists** → interactive: show current rules and ask which rule to add (add / view full file / cancel); kanban worker: take the rule from the task body.
6. **Append the rule** with `Edit` at the end of the `## Rules` section.
7. **Confirm:**

   ```text
   Rule added to .hermes-dev/rules/<area>.md:

   - [the rule]

   Total <area> rules: [count]
   ```

8. **STOP after Mode C completes.** Do not continue to Steps 2–4 below — those apply only to top-level axioms in `.hermes-dev/RULES.md`. Area rules belong only in `.hermes-dev/rules/<area>.md`.

**Common areas:** `api` (REST/GraphQL conventions), `frontend` (UI components, state management), `backend` (services, business logic), `database` (queries, migrations, schemas), `testing` (test patterns, coverage), `security` (auth, validation, sanitization).

## Step 2 — Read or create RULES.md

Check if `.hermes-dev/RULES.md` exists (Glob). If NOT → create it with the header and first rule:

```markdown
# Project Rules

> Short, actionable rules and conventions for this project. Loaded automatically by /aif-implement.

## Rules

- [new rule here]
```

If it exists → read it, then append the new rule at the end of the rules list.

## Step 3 — Write the rule

Use `Edit` to append the new rule as a `- ` list item at the end of the `## Rules` section.

Formatting rules:
- Each rule is a single `- ` line; short and actionable (one sentence).
- No categories, headers, or sub-lists — flat list only.
- No duplicates — if a rule with the same meaning already exists, report it and skip.
- Multiple rules at once (newlines or semicolons) → add each as a separate line.
- Preserve stable technical tokens verbatim (paths, commands, code identifiers, package/API names).

## Step 4 — Confirm

```text
Rule added to .hermes-dev/RULES.md:

- [the rule]

Total rules: [count]
```

## Rules

1. **One rule per line** — flat list, no nesting.
2. **No categories** — no headers inside the rules section.
3. **No duplicates** — check for same-meaning rules before adding.
4. **Actionable language** — clear directives ("Always...", "Never...", "Use...", "Routes must...").
5. **Fixed locations** — axioms in `.hermes-dev/RULES.md`, area rules in `.hermes-dev/rules/<area>.md`.
6. **Area discovery by filename** — an area rules file is active by existing under `.hermes-dev/rules/`; there is no config registry in Hermes.
7. **Ownership boundary** — this skill owns `.hermes-dev/RULES.md` and `.hermes-dev/rules/*.md`; all other context artifacts (DESCRIPTION.md, ARCHITECTURE.md, plans, specs) stay read-only unless explicitly requested.
