---
name: hermes-dev-gate-result
description: Use when acting as a Hermes kanban spec, verify, review, security, rules, or QA gate. Emit strict JSON gate_result verdicts and fail closed instead of marking blocked work done.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [kanban, gate-result, verification, review, security, dev-factory]
    related_skills: [hermes-agent, requesting-code-review, test-driven-development]
---

# Hermes Dev Gate Result

## Overview

Gate workers are not prose reviewers. They produce a final machine-readable verdict that downstream agents and orchestrators can parse without guessing.

Use `gate_result` on `kanban_complete` for non-blocking gates. For blocking gates, preserve the same JSON in `kanban_comment` if downstream workers need it, then route the task with `kanban_block` or request-changes follow-up work.

## When to Use

Use this skill when you are assigned or asked to run any Hermes developer gate:

- `spec` — spec/contract completeness before implementation
- `verify` — tests, builds, runtime checks, acceptance proof
- `review` — code quality and task-fit review
- `security` — secrets, injection, permission, data-safety review
- `rules` — project/AGENTS/SOUL/workflow compliance
- `qa` — end-to-end user-facing quality checks

Do not use this for ordinary implementation progress notes. Normal workers can put `changed_files`, `tests_run`, and `decisions` in metadata without a gate verdict.

## Contract v1

Every gate result is one JSON object:

```json
{
  "schema_version": 1,
  "gate": "verify",
  "status": "pass",
  "blocking": false,
  "blockers": [],
  "affected_files": [],
  "suggested_next": {
    "action": null,
    "reason": "No blocking findings."
  }
}
```

Allowed values:

| Field | Values |
|---|---|
| `gate` | `spec`, `verify`, `review`, `security`, `rules`, `qa` |
| `status` | `pass`, `warn`, `fail` |
| `blocking` | boolean |
| `blockers[].severity` | `info`, `warning`, `warn`, `error` |

Blocker item shape:

```json
{
  "id": "review-001",
  "severity": "error",
  "file": "optional/path.ts",
  "summary": "Human-readable short finding"
}
```

## How to Finish a Gate

1. Run real checks for the assigned gate. Completion criterion: every finding is backed by a command, file read, diff, screenshot, or provided context.
2. Build the `gate_result` JSON. Completion criterion: all required fields are present and allowed values are used.
3. If `status` is `pass` or non-blocking `warn`, call `kanban_complete(summary=..., metadata=..., gate_result=...)`. Completion criterion: the run metadata contains `gate_result`.
4. If `status` is `fail` or `blocking` is `true`, do not call `kanban_complete`. Add a `kanban_comment` with the JSON if needed, then call `kanban_block(reason=...)` or create a `request_changes` follow-up task. Completion criterion: the task is not fake-done.

## Status Semantics

- `pass`: no blockers; `blocking` must be `false`; `blockers` must be empty.
- `warn`: non-blocking risk or caveat; set `blocking=false` unless a human must decide before merge.
- `fail`: at least one blocker; set `blocking=true`; route rework/manual review.

## Suggested Next Actions

Use compact action names so orchestrators can parse them later:

- `null` — no next action
- `request_changes` — implementer should fix blockers
- `manual_review_required` — human/tech lead must decide
- `rerun_verify` — verification was inconclusive and should be rerun
- `blocked_external` — provider/access/infra outside the worker blocks progress

`reason` should be one sentence, not a log dump.

## Common Pitfalls

1. **Fake completion with blockers.** A `fail`/blocking verdict is not done. `kanban_complete` rejects it; use `kanban_block` or request changes.
2. **Prose-only review.** Downstream automation parses only `gate_result`, not a long summary.
3. **Missing evidence.** A gate result without real checks is a claim, not a verdict.
4. **Unbounded blockers.** Keep each blocker short and actionable; put logs in artifacts or comments if needed.
5. **Changing specs silently.** Review/verify/security gates consume specs and plans; they do not rewrite them unless the task explicitly asks.

## Verification Checklist

- [ ] `schema_version` is `1`
- [ ] `gate` and `status` use allowed values
- [ ] `blocking` matches the status and blocker severity
- [ ] Every blocker has `id`, `severity`, and `summary`
- [ ] `affected_files` lists only relevant paths
- [ ] `suggested_next.reason` is actionable
- [ ] Blocking/failing gates did not call `kanban_complete`
