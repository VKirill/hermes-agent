---
name: aif-security-checklist
description: >-
  Security audit of changed code — secrets, injection, auth/authz, input validation, unsafe
  shell/file handling, race conditions, prompt injection, and dependency risk. Emits a
  machine-readable gate_result with gate="security". Use before merge/release, or when the
  user says "security check", "audit this", "is this safe". This is the security gate skill
  (port of lee-to AI Factory /aif-security-checklist, adapted to Hermes).
tags:
  - aif
  - security
  - quality-gate
  - dev-factory
  - kanban
---

# aif-security-checklist — Security gate

Audit the changed scope for exploitable issues and emit a gate_result. Report findings; do not modify code (that is aif_implementer's job via a fix task).

## Hermes context
Runs as a kanban worker (usually under `aif_reviewer` or a dedicated security pass). Artifacts under `.hermes-dev/`. No `HANDOFF_MODE`/MCP/config.yaml. Read-only. Never read, exfiltrate, or echo actual secret values — report the location and the risk only.

## Step 0 — Scope
Gather changed files (`git diff --name-only <base>...HEAD` or the working tree). Read `.hermes-dev/skill-context/aif-security-checklist/SKILL.md` (**MANDATORY if it exists**) and any `.hermes-dev/rules/security*`.

## Audit checklist
- **Secrets:** hardcoded keys/tokens/passwords/cookies; secrets in logs; `.env` committed; secrets in error messages.
- **Injection:** SQL/NoSQL (unparameterized queries), command injection (shell built from input), XSS (unescaped output), path traversal, template/SSTI, deserialization.
- **AuthN/AuthZ:** missing/insufficient checks, IDOR (object access without ownership check), privilege escalation, broken session handling, missing rate limits on sensitive endpoints.
- **Input validation:** untrusted input reaching sinks without validation/sanitization; type/bounds/length; SSRF (server-side requests to attacker-controlled URLs).
- **Unsafe shell/file handling:** `eval`/`exec`, shell=True with interpolation, world-writable paths, TOCTOU on file ops, unsafe temp files.
- **Race conditions:** check-then-act without a lock/transaction, non-atomic multi-step state changes (e.g. balance/stock), concurrent write hazards.
- **Prompt injection (LLM code):** untrusted content flowing into prompts/tool calls without isolation; tool outputs treated as instructions.
- **Dependencies:** newly added deps — known-vulnerable/abandoned/typosquat; pinned vs floating; supply-chain risk.

## Severity → gate mapping
- `critical` / `high` → `error` (blocking).
- `medium` / `low` → non-blocking human `warning`.
- A single `error` finding sets `status: "fail"`, `blocking: true`.

## Output — findings + gate_result
Human summary grouped by severity (each: risk → `file:line` → concrete remediation), then append the final machine-readable block and pass it to `kanban_complete` (pass/warn) or `kanban_block` (fail):

```aif-gate-result
{
  "schema_version": 1,
  "gate": "security",
  "status": "fail",
  "blocking": true,
  "blockers": [
    { "id": "security-secret-1", "severity": "error", "file": "src/config.ts", "summary": "Hardcoded API secret present." }
  ],
  "affected_files": ["src/config.ts"],
  "suggested_next": { "action": "/aif-fix", "reason": "Remove and rotate the exposed secret." }
}
```
- `status` ∈ `pass|warn|fail`. `blockers` = error-severity findings only. `affected_files` = files audited/cited. `suggested_next.command` ∈ {/aif-fix, null}.

On `fail`, close the loop the same way aif-review does: create a fix task for `aif_implementer` (`--idempotency-key sec-fix:<task_id>`) and link it so re-audit waits.

## References

- `references/AUTH-PATTERNS.md` — good/bad authentication patterns: password hashing (argon2id/bcrypt), secure session cookies, minimal JWT claims.
- `references/PROMPT-INJECTION.md` — LLM security patterns: direct/indirect prompt injection, tool-call validation, output sanitization, RAG checklist.
- `references/RACE-CONDITIONS.md` — race-condition patterns: balance/double-spend, TOCTOU, optimistic locking, idempotency keys, distributed locks.
- `scripts/audit.sh` — quick automated pre-pass (secrets grep, .env tracking, npm audit, console noise, raw errors, security TODOs); it complements, never replaces, the manual checklist above.
