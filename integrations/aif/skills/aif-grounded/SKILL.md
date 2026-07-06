---
name: aif-grounded
description: >-
  Reliability gate for answers. Forces evidence-based reasoning, explicit uncertainty,
  and "insufficient information" instead of guesses. Use when the user says "be 100%
  sure", "no hallucinations", "only if verified", "grounded answer", or when stakes are
  high (security/finance/legal, changeable facts, prod-affecting decisions)
  (port of lee-to AI Factory /aif-grounded, adapted to Hermes).
tags:
  - aif
  - reliability
  - grounding
  - dev-factory
---

# aif-grounded — Reliability gate (no guessing)

This skill minimizes random / fabricated answers by enforcing a strict rule:

**Only provide the final answer if confidence is 100/100 based on evidence available.**

If confidence is not 100, **do not guess** and **do not implement**. Output a short "what's missing" checklist that explains what would be required to reach 100.

## Hermes context

- This is a reliability mode for answers, not a kanban pipeline gate — it emits no `aif-gate-result` block. It can be layered on top of any aif-* role work when the task demands verified facts.
- Evidence sources include the repo, command outputs, provided docs, authoritative external docs, and saved references in `.hermes-dev/reference/` (see `aif-reference`).
- **Autonomy:** in interactive sessions, ask for the missing source when verification is impossible. As a kanban worker, do not ask — return the INSUFFICIENT INFORMATION block in the handoff, or `kanban_block` with the exact missing evidence when the task cannot proceed without it.

## When to use

- The user requests maximum reliability ("only if you're sure", "no assumptions").
- The request includes changeable facts (versions, "latest", policies, prices, schedules).
- The request is security/finance/legal/medical adjacent (high stakes).
- You're resuming after context loss and need to avoid accidental assumptions.

## Workflow

### Step 0 — Load skill context

**Read `.hermes-dev/skill-context/aif-grounded/SKILL.md` — MANDATORY if it exists.** It contains project-specific rules accumulated by `/aif-evolve` from patches, codebase conventions, and tech-stack analysis.

How to apply skill-context rules:
- Treat them as **project-level overrides** for this skill's general instructions; on conflict, **the skill-context rule wins** (more specific context takes priority — same principle as nested CLAUDE.md files). No conflict → apply both.
- Do NOT ignore skill-context rules even if they seem to contradict this skill's defaults — they exist because the project's experience proved the default insufficient.
- **CRITICAL:** skill-context rules apply to ALL outputs of this skill — including the response format, evidence requirements, and confidence assessment. If a rule says "analysis MUST include X" or "confidence MUST account for Y" — you MUST comply.
- **Enforcement:** after generating any output, verify it against all skill-context rules; fix violations before presenting.

### Step 1 — Classify the request

Classify into one of:
1. **Repo-grounded** — can be answered purely from the local codebase and command outputs.
2. **Doc-grounded** — requires authoritative docs/specs/logs provided by the user, saved in `.hermes-dev/reference/`, or accessible via tooling.
3. **External-facts** — depends on changeable facts outside the repo (must be verified, otherwise refuse).

### Step 2 — Define evidence and unknowns

Before answering, list:
- **Evidence sources** you will use (files, command outputs, provided docs, references).
- **Unknowns** (anything not present in evidence).

Hard rule: if a claim is not supported by evidence, it becomes an **unknown** (not an assumption).

### Step 3 — Mandatory verification for changeable facts

If the request contains any changeable fact ("latest", "current", "today", "default in vX", "does library Y support Z now"):
- Verify via authoritative docs/specs, release notes, or logs.
- If verification is not possible with available tools/context, return **INSUFFICIENT INFORMATION** and name the needed source (link excerpt, version, log output) — ask for it interactively, or put it in the handoff/block reason as a kanban worker.

### Step 4 — Confidence gate

Compute a confidence score 0–100:
- **100** only if every factual claim is supported by evidence you can point to (repo files, command outputs, provided docs), and there are **no open unknowns**.
- If any unknown remains → confidence < 100 → do not answer/implement.

### Step 5 — Output format (strict)

If confidence is **100**:
```
Answer:
<final answer or patch summary>

Confidence: 100/100
Evidence:
- <file/command/doc used>

Checks:
- <3 concrete checks someone can run/inspect to confirm>
```

If confidence is **< 100**:
```
Result: INSUFFICIENT INFORMATION (no guessing)
Current confidence: <N>/100
Why not 100:
- <top reasons>

Missing evidence:
- <what exact file/output/doc is needed>

To reach 100:
- <1–3 concrete asks or commands for the user to run and paste output>
```

## Artifact ownership

- Primary ownership: none. This skill is a reliability gate for answers, not an artifact-producing workflow.
- Write policy: do not create or modify project artifacts by default.
- Evidence comes from the repo, command outputs, provided docs, `.hermes-dev/reference/`, and authoritative sources — there is no config file to consult.

## Implementation guardrail

If the user asks for code changes:
- You may explore the repo and propose what evidence is needed.
- Only apply patches once confidence can be 100 (e.g., requirements are precise + you can verify build/tests or equivalent checks).
- If the repo lacks a verification path (no build/tests and behavior can't be validated), do not claim 100; return INSUFFICIENT INFORMATION and propose the minimal validation needed.
