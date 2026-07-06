---
name: aif-roadmap
description: >-
  Create or update the project roadmap with major milestones — a strategic checklist of
  high-level goals at .hermes-dev/plans/ROADMAP.md, plus an evidence-based progress check
  mode. Use when the user says "roadmap", "project plan", "milestones", or
  "what to build next" (port of lee-to AI Factory /aif-roadmap, adapted to Hermes).
tags:
  - aif
  - roadmap
  - planning
  - dev-factory
---

# aif-roadmap — Strategic Project Planning

Create and maintain a high-level project roadmap with major milestones. Milestones are strategy; granular task breakdown belongs to `aif-plan`.

## Hermes context (how this differs from lee-to's original)

- Runs interactively or as a kanban worker on the `departments` board. Native kanban is the handoff layer — **no `.ai-factory/config.yaml`**; paths are fixed: the roadmap lives at **`.hermes-dev/plans/ROADMAP.md`** in the target app (`~/Work/apps/<slug>/`); `DESCRIPTION.md` and `ARCHITECTURE.md` at the project root.
- **Autonomous mode:** no interactive questions. Where the original asks (gather vision, confirm save, confirm marking milestones), decide from evidence: use the task body as the vision, save directly, mark milestones only on **strong** evidence, and report everything in the kanban handoff. Block only when creating a roadmap with no vision in the task body AND nothing to analyze in the codebase. Interactive use keeps the original questions.

## Step 0 — Load project context

Read if present in the target workspace:
- `DESCRIPTION.md` (project root) — tech stack, architecture, conventions, non-functional requirements
- `ARCHITECTURE.md` (project root) — chosen pattern, folder structure, module boundaries
- `.hermes-dev/RULES.md` + `.hermes-dev/rules/*` — hard project rules
- **`.hermes-dev/skill-context/aif-roadmap/SKILL.md` — MANDATORY if it exists.** Project rules accumulated by `aif-evolve`; treat as project-level overrides: on conflict **skill-context wins** over this file, otherwise apply both. They apply to ALL outputs, including the ROADMAP.md template below (a base structure — if a rule says "the roadmap MUST include X" or "milestones MUST have Y", augment it). Verify the generated artifact against these rules before finishing; fix violations first.
- The kanban task body + parent handoffs (`hermes kanban --board departments show <id>`).

## Step 1 — Determine mode

- Argument/task body says `check` → **Mode 3: Check Progress** (requires the roadmap to exist).
- Otherwise, does `.hermes-dev/plans/ROADMAP.md` exist?
  - **No** → Mode 1: Create Roadmap
  - **Yes** → Mode 2: Update Roadmap

---

## Mode 1 — Create Roadmap (first run)

**1.1 Gather input.**
- Vision/requirements provided (arguments or task body) → primary input for milestones.
- Nothing provided — interactive: ask "What are the major goals?" with options (1. describe the vision, 2. analyze codebase and suggest, 3. both), and follow up on priorities/deadlines (specify | logical order | skip). Autonomous: analyze the codebase and derive milestones; if there is also no codebase, **block** with "no vision in task body and empty codebase".

**1.2 Explore the codebase** to see what is already built:
- `Glob` for project structure (key directories, modules)
- `Grep` for implemented features (routes, models, services)
- `git log --oneline -20` for completed work

**1.3 Generate ROADMAP.md** at `.hermes-dev/plans/ROADMAP.md`:

```markdown
# Project Roadmap

> <project vision — one-liner from DESCRIPTION.md or the brief>

## Milestones

- [ ] **Milestone Name** — short description of what this achieves
- [ ] **Milestone Name** — short description of what this achieves
- [x] **Milestone Name** — short description (already done per codebase analysis)

## Completed

| Milestone | Date |
|-----------|------|
| Milestone Name | YYYY-MM-DD |
```

**Rules for milestones:**
- Each milestone is a **high-level goal**, not a granular task (that's `aif-plan`).
- 5–15 milestones is the sweet spot — fewer is too vague, more is too granular.
- Order by logical sequence (dependencies first).
- Mark already-completed milestones `[x]` and add them to the Completed table with today's date.

**1.4 Confirm & save.**
- Interactive: show the roadmap and ask (looks good — save | add milestones | remove/modify | rewrite with better input); apply changes, then save.
- Autonomous: save directly and return the milestone list in the handoff.

---

## Mode 2 — Update Roadmap (subsequent runs)

**2.1 Read current state:** `.hermes-dev/plans/ROADMAP.md`, `DESCRIPTION.md`, and a brief codebase scan for changes since the last update.

**2.2 Determine action.**
- Explicit changes requested (arguments/task body) → apply them directly.
- Nothing specified — interactive: ask (review progress | add milestones | reprioritize | rewrite). Autonomous: run a progress review (2.3) and apply it; never rewrite or reorder without an explicit request.

**2.3 Review progress.**
- Scan the codebase for evidence of completed milestones; for each unchecked milestone, judge whether the work appears done.
- Interactive: propose ("These milestones appear done: **Name** — [evidence: files exist, routes implemented] — mark them?") and wait for confirmation.
- Autonomous: mark only milestones with **strong** evidence; list partial ones in the handoff without marking.
- When marking: flip `- [ ]` → `- [x]`, add a Completed-table entry with today's date.

**2.4 Add new milestones** — insert them in logical (dependency) order among the existing ones.

**2.5 Reprioritize** — reorder per the requested priorities (interactive: show current order first).

**2.6 Save & summarize:**

```
## Roadmap Updated
Total milestones: N | Completed: X/N
Next up: **Milestone Name**

To start the next milestone:
  aif-plan <milestone description>  → implementation plan (+ project/branch flow)
  aif-implement                     → executes the plan
```

---

## Mode 3 — Check Progress (`check`)

Automated, non-interactive scan — analyze the codebase and mark completed milestones. **Requires** `.hermes-dev/plans/ROADMAP.md` to exist; if missing, report "create the roadmap first (run aif-roadmap)".

**3.1** Read the roadmap and `DESCRIPTION.md` (tech-stack context).

**3.2** For every `- [ ]` milestone:
- Decide what evidence would prove it done (files, routes, models, configs, tests).
- Search for that evidence with `Glob`/`Grep`; check `git log --oneline --all -30` for related commits.
- Score: **done** (strong evidence) | **partial** (work started) | **not started**.

**3.3** Report findings:

```
## Roadmap Progress Check

Done (ready to mark):
- **User Authentication** — found: src/auth/, JWT middleware, login/register routes

In Progress:
- **Payment Integration** — src/payments/ exists but the Stripe webhook handler is missing

Not Started:
- **Admin Dashboard**
```

**3.4** Apply: mark **done** milestones `[x]` + Completed-table entries with today's date (interactive: after confirmation; autonomous: directly, evidence listed in the handoff). Leave partial/not-started untouched. Show `Completed: X/N, next up: **Name**`.

---

## ROADMAP.md format (canonical)

```markdown
# Project Roadmap

> <project vision — one-liner>

## Milestones

- [ ] **Name** — short description
- [x] **Name** — short description

## Completed

| Milestone | Date |
|-----------|------|
| Name | YYYY-MM-DD |
```

## Critical rules

1. **Milestones are high-level** — each is a major feature or capability, not a task.
2. **ROADMAP.md is the source of truth** — always read it before modifying.
3. **Never remove milestones silently** — interactive: confirm first; autonomous: never remove at all (only add, mark, or reorder on explicit request).
4. **Completed table tracks history** — every checked milestone gets a dated entry.
5. **NO implementation** — this skill only plans; `aif-plan` starts a feature, `aif-implement` executes it.
6. **Ownership boundary** — this skill owns roadmap structure/content; `aif-implement` may only mark milestones completed when implementation evidence is clear.
