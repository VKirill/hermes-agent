---
name: aif-specify
description: >-
  Turn a rough kanban triage task / PM brief into a concrete implementation spec — goal, scope,
  acceptance criteria, contracts, constraints, out-of-scope, risks, open questions — then hand off
  to aif_planner. Use when a dev task is unclear/large/cross-domain/risky and needs a spec before
  planning. This is the aif_specifier role skill (Hermes AIF; upstream of aif-plan).
tags:
  - aif
  - spec
  - dev-factory
  - kanban
---

# aif-specify — write the spec

Convert an unclear brief/triage idea into bounded, testable requirements so downstream stages don't drift. You do NOT plan tasks or write production code — you produce the spec.

## Hermes context
Runs as a kanban worker under `aif_specifier`. Artifacts under `.hermes-dev/specs/`. No `HANDOFF_MODE`/MCP/config.yaml. Autonomous: if required context is missing, **block with the precise question** — do not guess.

## Step 0 — Read
The kanban task + parent handoffs, `DESCRIPTION.md` and `ARCHITECTURE.md` at the project root, `.hermes-dev/RULES.md`, and `.hermes-dev/skill-context/aif-specify/SKILL.md` (**MANDATORY if it exists**). Inspect existing code where a path is given.

## Step 1 — Produce the spec
Write `.hermes-dev/specs/<slug>.md` with:
- **Goal** — 1–2 lines, the outcome.
- **In scope / Out of scope** — explicit boundaries (out-of-scope prevents drift).
- **Acceptance criteria** — concrete, testable checks the verifier can confirm.
- **Contracts / interfaces** — API shapes, data models, CLI, file formats.
- **Constraints** — performance, security, dependencies, compatibility.
- **Risks & open questions** — what could go wrong; unknowns.
- **New app?** — if this is a new application (no existing folder/repo), note it so `aif_planner` bootstraps a project + folder `~/Work/apps/<slug>/` (see `aif-plan` Step 3.5).

## Step 2 — Block if genuinely underspecified
If the goal can't be made testable without input you don't have, `kanban_block` with the exact missing input. Do not invent requirements.

## Step 3 — Hand off
Complete the spec task with a structured handoff (spec path, key decisions, open questions). The plan stage (`aif_planner` / `aif-plan`) picks it up next.

## Rules
Spec only — no production code (a tiny clarification snippet is fine only if explicitly scoped). Acceptance criteria must be testable. Keep user-facing summaries Russian/PM-style; developer instructions English-first. Never redo the planner's or implementer's job.
