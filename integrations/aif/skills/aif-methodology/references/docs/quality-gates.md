[AIF methodology](../../SKILL.md) · [Development Workflow](workflow.md) · [Core Skills](skills.md)

> Ported from lee-to AI Factory `docs/quality-gates.md` (`aif-gate-result` contract), adapted to
> the Hermes `gate_result` contract: the same JSON, but delivered through the kanban tool boundary
> (`kanban_complete` / `kanban_block`), with the gate list extended by Hermes's own gates.

# Quality Gates

Quality gates keep their normal human-readable Markdown reports, then emit one final
machine-readable block. In Hermes the consumer is the kanban workflow core
(`hermes_cli/kanban_workflow.py`): it parses only the structured `gate_result`, never prose.

Delivery:
- **Kanban worker** (the normal case): the gate passes the JSON via the kanban tool call —
  `kanban_complete` for `pass`/`warn`, `kanban_block` for `fail`. The tool boundary **requires** a
  valid `gate_result` on review/verify completion: malformed or missing output is rejected back to
  the live worker to fix immediately, and is never treated as PASS.
- **Interactive session**: the gate appends the same JSON as the last fenced block in its output
  (fence label `aif-gate-result`, kept for lee-to compatibility). Orchestrators parse only the
  last fenced block.

Supported gates:
- `aif-verify` → `gate: "verify"`
- `aif-review` → `gate: "review"`
- `aif-security-checklist` → `gate: "security"`
- `aif-rules-check` → `gate: "rules"`
- `aif-qa` → `gate: "qa"` (Hermes extension)
- `aif-qa-check` → `gate: "qa-check"` (Hermes extension)
- `aif-specify` → `gate: "spec"` (Hermes extension — optional pipeline pre-stage)

The block must be valid JSON and must appear after the human summary.

## Schema

```aif-gate-result
{
  "schema_version": 1,
  "gate": "verify",
  "status": "fail",
  "blocking": true,
  "blockers": [
    {
      "id": "verify-task-1",
      "severity": "error",
      "file": "src/example.ts",
      "summary": "Required behavior is missing."
    }
  ],
  "affected_files": ["src/example.ts"],
  "suggested_next": {
    "command": "aif-fix",
    "reason": "Blocking implementation gaps remain."
  }
}
```

Rules:
- `schema_version` is currently `1`.
- `gate` is one of `spec`, `verify`, `review`, `security`, `rules`, `qa`, or `qa-check`.
- `status` is one of `pass`, `warn`, or `fail`.
- `blocking` is a boolean.
- `blockers` contains only findings that should block the current gate.
- `blockers[].severity` uses `error` or `warning`; security `critical`/`high` maps to `error`,
  while `medium`/`low` normally remains a non-blocking human warning.
- `blockers[].id` must be **stable across review rounds** (derived from source+text) — the
  convergence gate matches findings by id to classify them as `still_blocking` / `resolved` / `new`.
- `affected_files` is a predictable top-level array of files the gate actually evaluated or cited.
  It is not limited to blocker files. Use `[]` when no files apply.
- `suggested_next.command` is selected from the global allowlist: `aif-fix`, `aif-rules`,
  `aif-architecture`, `aif-roadmap`, `aif-commit`, or `null`. Individual gates may document
  narrower subsets.

## Status Examples

Pass:

```aif-gate-result
{
  "schema_version": 1,
  "gate": "review",
  "status": "pass",
  "blocking": false,
  "blockers": [],
  "affected_files": ["src/auth/login.ts"],
  "suggested_next": {
    "command": "aif-commit",
    "reason": "Review found no blocking issues."
  }
}
```

Warn:

```aif-gate-result
{
  "schema_version": 1,
  "gate": "rules",
  "status": "warn",
  "blocking": false,
  "blockers": [],
  "affected_files": [],
  "suggested_next": {
    "command": "aif-rules",
    "reason": "Rules are missing or ambiguous for the changed scope."
  }
}
```

Fail:

```aif-gate-result
{
  "schema_version": 1,
  "gate": "security",
  "status": "fail",
  "blocking": true,
  "blockers": [
    {
      "id": "security-secret-1",
      "severity": "error",
      "file": "src/config.ts",
      "summary": "A hardcoded secret is present."
    }
  ],
  "affected_files": ["src/config.ts"],
  "suggested_next": {
    "command": "aif-fix",
    "reason": "Remove the exposed secret and rotate it."
  }
}
```

## What the workflow core does with a gate result

For cards on the `--workflow aif` stage machine (see
[Development Workflow](workflow.md#hermes-stage-machine)):

- `pass`/`warn` via `kanban_complete` → the card advances to the next stage.
- `fail` via `kanban_block(gate_result)` → the convergence gate (`evaluate_review_gate`) compares
  `blockers[]` against previous rounds by stable id:
  - blockers remain and iteration < cap → **rework**: the card returns to `implementing` with the
    findings carried over (a fix task for `aif_implementer`, idempotency-key `fix:<id>`);
  - iteration ≥ cap (`kanban.max_review_iterations`, default 3) → **manual_review_required**;
  - `closure_first` strategy: previous findings resolved but new blockers appeared →
    **manual_review_required (new_blockers_after_rework)**;
  - malformed gate output when previous findings exist → **manual_review_required
    (malformed_review_output)** — never PASS.
- Every decision is posted as an auto **Review Gate Summary** comment on the card.

Department law (see `aif-methodology` SKILL.md): a fail verdict MUST spawn a fixer — never leave a
blocker without a fix task.

## Compatibility

Manual workflows continue to read the human Markdown summaries. Existing `WARN`, `ERROR`, `PASS`,
and `FAIL` labels can remain in those summaries when they are useful for people.

The machine contract is only the structured `gate_result` (tool parameter in worker mode; final
fenced JSON block in interactive output). Orchestrators should ignore earlier Markdown headings,
bullets, and examples.

## Ownership

Quality gates remain read-only for context artifacts by default. If a gate finds stale
architecture, roadmap, or rules context, it should suggest the owner skill instead of editing the
artifact directly.

Exceptions stay with existing skill contracts. For example, `aif-security-checklist ignore <item>`
may write the security ignored-item artifact (`.hermes-dev/SECURITY.md`), but normal security audit
findings are report output.

## See Also

- [Development Workflow](workflow.md) — where gates fit into the workflow and stage machine
- [Core Skills](skills.md) — skill reference for each quality gate
- [Configuration](configuration.md) — convergence/iteration keys (`kanban.*`)
