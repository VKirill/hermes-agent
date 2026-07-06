# Context Gates and Artifact Ownership Contract

Canonical contract for AI Factory workflow skills, ported from lee-to AI Factory
and adapted to Hermes (paths under `.hermes-dev/`, skills instead of slash
commands, autonomous kanban workers). This file defines:
- which skill owns each artifact,
- which skills consume artifacts as read-only context,
- and how context gates behave in normal vs strict verification.

Skills referenced below that are not yet ported are part of the full-port roadmap
(see `aif-methodology/references/full-port-roadmap.md`) — the ownership contract
already reserves their lanes.

## Skill-to-Artifact Matrix

| Skill              | Primary write ownership                                                                     | Read-only context                                                                                                                       | Approved exceptions                                                                                                                                       |
|--------------------|---------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `aif` (setup)      | `DESCRIPTION.md` (project root), `AGENTS.md` (setup map), skill installation review         | Existing project files and context artifacts                                                                                             | May invoke `aif-architecture` to create/update the project-root `ARCHITECTURE.md` during setup                                                               |
| `aif-architecture` | `ARCHITECTURE.md` (project root)                                                            | `DESCRIPTION.md` (project root)                                                                                                           | May update `DESCRIPTION.md` architecture pointer and `AGENTS.md` context table                                                                                |
| `aif-roadmap`      | `.hermes-dev/plans/ROADMAP.md`                                                              | `DESCRIPTION.md` and `ARCHITECTURE.md` (project root)                                                                                     | `aif-implement` may mark completed milestones after implementation                                                                                            |
| `aif-rules`        | `.hermes-dev/RULES.md` (+ `.hermes-dev/rules/*`)                                            | Existing project context                                                                                                                  | None                                                                                                                                                          |
| `aif-plan`         | `.hermes-dev/plans/<slug>.md`                                                               | `DESCRIPTION.md` and `ARCHITECTURE.md` (project root), `.hermes-dev/research/RESEARCH.md`                                                 | `aif-improve` may refine existing plan files                                                                                                                  |
| `aif-implement`    | Plan progress updates (checkboxes)                                                          | `.hermes-dev/RULES.md`, `ARCHITECTURE.md` and `DESCRIPTION.md` (project root), `.hermes-dev/skill-context/*`, limited recent patches      | May update `DESCRIPTION.md` and `ARCHITECTURE.md` only when stack/structure changed; may update `.hermes-dev/plans/ROADMAP.md` milestone completion          |
| `aif-fix`          | `.hermes-dev/fixes/*` (plan mode), `.hermes-dev/patches/*.md`                               | `DESCRIPTION.md` (project root), `.hermes-dev/skill-context/*`, limited recent patches (fallback)                                         | None (context artifacts remain read-only by default)                                                                                                          |
| `aif-evolve`       | `.hermes-dev/evolutions/*.md`, `.hermes-dev/evolutions/patch-cursor.json`, `.hermes-dev/skill-context/*` | `DESCRIPTION.md` (project root), `.hermes-dev/patches/*.md` (processed incrementally)                                        | None                                                                                                                                                          |
| `aif-docs`         | `README.md`, project docs, `AGENTS.md` documentation section                                | Project/context files for factual docs                                                                                                    | README stays fixed at the project root                                                                                                                        |
| `aif-explore`      | `.hermes-dev/research/RESEARCH.md` only                                                     | All context and codebase files for analysis                                                                                               | None                                                                                                                                                          |
| `aif-commit`       | Git commit object/message only                                                              | Context artifacts are read-only gates                                                                                                     | No context artifact writes by default                                                                                                                         |
| `aif-review`       | Review output + gate_result only                                                            | Context artifacts are read-only gates                                                                                                     | On fail: creates the fix task for `aif_implementer` (kanban), never edits context artifacts                                                                    |
| `aif-verify`       | Verification report + gate_result                                                           | Context artifacts are read-only gates                                                                                                     | On fail: blocks the kanban task and suggests `/aif-fix` (autonomous — no user confirmation); no default context artifact writes                               |

## Artifact Update Policy (Recommended)

- **Owner writes only:** An artifact should be updated by its owner skill.
- **Implement may do factual deltas:** `aif-implement` may update
  the project-root `DESCRIPTION.md` and `ARCHITECTURE.md` only when
  implementation materially changed stack/structure; it may mark roadmap
  milestones complete when evidence is clear.
- **Verify stays read-only:** `aif-verify` reports drift and suggests the owner
  skill; it does not update context artifacts.
- **Rules are explicit:** Only `aif-rules` edits `.hermes-dev/RULES.md`. Other
  skills may propose candidate rules and point at `aif-rules` in their handoff.

## Context Gates (commit/review/verify)

These skills evaluate context consistency against:
- `ARCHITECTURE.md` (project root)
- `.hermes-dev/plans/ROADMAP.md` (optional, graceful if missing)
- `.hermes-dev/RULES.md` (optional, graceful if missing)

Gate outputs must use:
- `WARN` for non-blocking mismatches or missing optional files
- `ERROR` for blocking violations

For machine-readable orchestration, supported quality gates append a final
`aif-gate-result` JSON block using lowercase `pass` / `warn` / `fail` status
values (see `GATE-RESULT-CONTRACT.md`), passed to the department via
`kanban_complete` (pass/warn) or `kanban_block` (fail). The human `WARN` /
`ERROR` labels above remain readable report labels, not the machine contract.

### Architecture Gate
- **Pass:** Changes follow documented module/layer boundaries.
- **Warn:** Architecture document appears stale or mapping is ambiguous.
- **Fail:** Clear boundary/dependency violation against explicit architecture rules.

### Rules Gate
- **Pass:** Changes comply with explicit project rules.
- **Warn:** Rule relevance is uncertain or cannot be verified confidently.
- **Fail:** Clear violation of an explicit rule in `.hermes-dev/RULES.md`.

### Roadmap Gate
- **Pass:** Changes align with an active milestone or approved roadmap direction.
- **Warn:** `.hermes-dev/plans/ROADMAP.md` missing, ambiguous milestone mapping, or no
  milestone linkage for `feat`/`fix`/`perf` work.
- **Fail (strict verify only):** Clear mismatch with roadmap direction after all
  available roadmap context is considered.

## Standalone Rules Gate

`aif-rules-check` is the standalone, read-only rules-only companion to these
context gates.

- It evaluates the resolved rules hierarchy plus changed files/diff and reports
  `PASS` / `WARN` / `FAIL`.
- Missing or non-applicable rules remain `WARN`.
- Explicit hard-rule violations may become `FAIL`.
- This does not change the human `WARN` / `ERROR` reporting labels used by
  `aif-commit`, `aif-review`, and `aif-verify`; `aif-review` and `aif-verify`
  still append the shared machine-readable gate result when they act as quality
  gates.

## Threshold Decisions (Resolved)

### Verify normal mode
- Architecture/rules clear violations: **fail**
- Roadmap mismatch: **warn** unless contradiction is explicit and severe
- Missing milestone linkage for `feat`/`fix`/`perf`: **warn**

### Verify strict mode
- Architecture clear violations: **fail**
- Rules clear violations: **fail**
- Roadmap clear mismatch: **fail**
- Missing milestone linkage for `feat`/`fix`/`perf` when `.hermes-dev/plans/ROADMAP.md`
  exists: **warn**

### Commit and review mode
- Context gates are read-only and non-destructive (report + gate_result only —
  never edit context artifacts).
- Missing roadmap linkage for `feat`/`fix`/`perf`: **warn** by default.
- In Hermes, `aif-review` IS a blocking gate: a clear architecture/rules
  violation keeps its gate_result at `fail` (kanban_block + fix task) even with
  zero critical code findings — see the aif-review SKILL.md. `aif-commit`
  context gates stay warn-by-default.
