[← Skill Evolution](evolve.md) · [AIF methodology](../../SKILL.md) · [Security →](security.md)

> Ported from lee-to AI Factory `docs/plan-files.md`. Paths fixed to the `.hermes-dev/` layout;
> the `ai-factory audit-artifacts` CLI is not ported (the frontmatter convention is kept as a
> manual/gate-checkable convention); skill acquisition retargeted to `~/.hermes/skills/`.

# Plan Files

The AIF department uses markdown files to track implementation plans. Paths are fixed — there is
no config-based relocation.

| Source | Plan File | After Completion |
|--------|-----------|------------------|
| `aif-plan` | `.hermes-dev/plans/<slug>.md` (slug: lowercase, hyphenated, ≤50 chars; branch name may serve as the stem) | Keep (archived later by `aif-archive`) |
| `aif-fix` (plan-first mode) | `.hermes-dev/fixes/FIX_PLAN.md` | Deleted by `aif-fix` after successful execution (default file only) |

lee-to's separate fast-plan file (`PLAN.md`) and the `workflow.plan_id_format: sequential`
numbering (`NNNN_` prefixes) are n/a in Hermes: all plans live in `.hermes-dev/plans/` under slug
names. If a project adopts numbered plans manually, `aif-archive` preserves the filenames as-is.

## Archive Lifecycle

When plans accumulate, `aif-archive` moves completed plans to `.hermes-dev/archive/plans/`:

```
.hermes-dev/plans/<plan>.md  →  (all tasks [x])  →  .hermes-dev/archive/plans/<plan>.md
```

- Original filenames are preserved
- An `archived: YYYY-MM-DD` field is added to the plan's YAML frontmatter
- Archived plans are excluded from plan discovery by `aif-implement`, `aif-verify`, `aif-improve`

Roadmap snapshots: `aif-archive --roadmap` trims closed milestones from
`.hermes-dev/plans/ROADMAP.md` into dated snapshots under `.hermes-dev/archive/roadmap/`.

## Artifact Ownership Quick Map

To avoid ownership conflicts, artifact writers are skill-scoped:

| Artifact                                                          | Primary owner skill  | Notes                                                                             |
|-------------------------------------------------------------------|----------------------|-----------------------------------------------------------------------------------|
| `DESCRIPTION.md` (project root)                                   | `aif`                | `aif-implement` may update only when implementation context actually changed      |
| `ARCHITECTURE.md` (project root)                                  | `aif-architecture`   | `aif-implement` may update structure notes when implementation changes structure  |
| `.hermes-dev/plans/ROADMAP.md`                                    | `aif-roadmap`        | `aif-implement` may mark completed milestones with evidence                       |
| `.hermes-dev/RULES.md`, `.hermes-dev/rules/<area>.md`             | `aif-rules`          | top-level conventions plus area-rule files                                        |
| `.hermes-dev/research/RESEARCH.md`                                | `aif-explore`        | explore-mode writable artifact                                                    |
| `.hermes-dev/plans/<slug>.md`                                     | `aif-plan`           | `aif-improve` refines existing plans                                              |
| `.hermes-dev/fixes/FIX_PLAN.md`, `.hermes-dev/patches/*.md`       | `aif-fix`            | bug-fix learning loop artifacts                                                   |
| `.hermes-dev/skill-context/*`                                     | `aif-evolve`         | project-specific skill overrides derived from patches                             |
| `.hermes-dev/evolution/*.md`, `.hermes-dev/evolution/patch-cursor.json` | `aif-evolve`   | evolution logs + incremental cursor state                                         |
| `.hermes-dev/archive/plans/*.md`, `.hermes-dev/archive/roadmap/*.md` | `aif-archive`     | archived plan files and dated roadmap snapshots                                   |

Quality skills (`aif-commit`, `aif-review`, `aif-verify`) treat these files as read-only context by
default.

## Artifact Metadata

Markdown artifacts may carry lightweight YAML frontmatter for traceability. The schema is
intentionally small: it gives teams enough traceability to catch broken links and stale downstream
artifacts without requiring a full artifact-management system.

> lee-to ships an `ai-factory audit-artifacts` CLI that validates these links. That CLI is **not
> ported** to Hermes — treat the schema below as a convention. `aif-verify`/`aif-review` may check
> obvious link breakage as part of consistency checks, and a dedicated audit can be run as an
> ad-hoc task when a project accumulates enough linked artifacts to need one.

```markdown
---
id: spec-auth-login
type: spec
status: accepted
owners: [platform]
depends_on:
  - adr-auth-session
affects:
  - plan-auth-login
  - docs-auth
supersedes:
  - adr-auth-jwt
---
```

Supported fields:

| Field | Required | Meaning |
|-------|----------|---------|
| `id` | Yes | Stable unique identifier. Prefer lowercase kebab-case with a type prefix, for example `spec-auth-login`, `adr-auth-session`, `plan-password-reset`, `docs-api-auth`, or `tests-checkout-flow`. Keep it stable when files move. |
| `type` | Recommended | Artifact kind. Recommended values: `spec`, `requirement`, `plan`, `adr`, `architecture`, `roadmap`, `docs`, `tests`, `qa`, `code`, `rules`, `research`, `patch`. |
| `status` | Recommended | Lifecycle state. Recommended values: `draft`, `proposed`, `accepted`, `active`, `in_progress`, `done`, `deprecated`, `obsolete`, `superseded`. |
| `owners` / `owner` | Recommended | Team, role, or person responsible for review when the artifact is affected. Prefer team owners such as `platform`, `frontend`, `backend`, `security`, `infra`, `qa`, `docs`, or `product`. |
| `depends_on` | Optional | Upstream artifacts this artifact relies on. Use it when the current artifact cannot be safely changed without checking another artifact. |
| `affects` | Optional | Downstream artifacts that should be reviewed when this artifact changes. Use it to make PR impact review explicit. |
| `implements` | Optional | Requirements, specs, or decisions implemented by this artifact. Common for `code` and `plan` artifacts. |
| `verifies` | Optional | Requirements, specs, or decisions verified by this artifact. Common for `tests` and `qa` artifacts. |
| `documents` | Optional | Requirements, specs, or decisions described by this artifact. Common for `docs` artifacts. |
| `supersedes` | Optional | Older artifacts replaced by this artifact. Common for ADRs and specs. Mark the older artifact `status: superseded` when possible. |

Relationship guidance:

- `depends_on` points upstream: a plan may depend on a spec, an ADR, and architecture guidance.
- `affects` points downstream: a changed ADR may affect architecture, plans, tests, and docs that
  need review.
- `implements`, `verifies`, and `documents` provide reverse traceability for implementation, test,
  and documentation coverage.
- `supersedes` keeps history while making the newer source of truth explicit.

Scalar values, inline arrays, and YAML-style lists are all acceptable:

```markdown
depends_on: adr-auth-session
affects: [plan-auth-login, docs-auth]
verifies:
  - spec-auth-login
```

Findings worth flagging when auditing links manually (lee-to's severity model, kept as guidance):

| Finding | Severity |
|---------|----------|
| Duplicate `id` | Fail |
| Unknown relation target | Fail |
| Self-reference | Fail |
| `depends_on` cycle | Fail |
| Missing `type`, `status`, or `owner` / `owners` | Warn |
| Spec with no dependency/impact links | Warn |
| Spec without incoming `implements`, `verifies`, or `documents` coverage | Warn |
| Accepted ADR without `affects` links | Warn |

When a change touches an artifact with downstream links, include an impact note that records the
decision for each affected artifact:

```markdown
## Artifact Impact

Changed:
- adr-auth-session

Reviewed:
- architecture-auth: updated
- spec-auth-login: reviewed-ok
- tests-auth-session: deferred, follow-up #123
```

## Research File (Optional)

`.hermes-dev/research/RESEARCH.md` is a persisted exploration artifact. Use it to capture
constraints, decisions, and open questions during `aif-explore` so a later session (or the next
pipeline stage) can feed the same context into `aif-plan`.

When research influences a plan, `aif-plan` copies the relevant Active Summary into
`## Research Context`. That embedded copy is the committed requirements snapshot for implementation
and verification. The live research file may change later; downstream skills compare the source
revision and warn on drift instead of silently applying newer research to an older plan.

Plans created before revision markers were introduced may contain a `Source:` or `Reference:` line
to `RESEARCH.md` without `Updated:` or `SHA256:` metadata. Downstream skills intentionally treat
that as an unverified research link and emit a legacy compatibility `WARN [research-drift]`; they
still execute against the embedded plan context instead of silently applying the current Active
Summary.

Typical structure:
- `## Active Summary (input for aif-plan)` — compact, up-to-date snapshot
- `## Sessions` — append-only history (keep prior notes verbatim)

## Original Request

When the user (or the kanban task body) supplies a request to `aif-plan`, the plan includes
`## Original Request` with the request preserved as raw source input.

Parsing removes only recognized command tokens in command positions (mode words and flags);
matching words inside the user's actual request are not removed. After token removal, `aif-plan`
trims only outer whitespace introduced by parsing. It preserves internal whitespace, line breaks,
wording, casing, and punctuation exactly. Downstream plan rewrites, including `aif-improve`, must
preserve `## Original Request` verbatim and must not translate, summarize, normalize, or rewrite
it even when the plan's prose language differs.

This section is omitted only when the plan is created solely from `RESEARCH.md` without an explicit
user request; in that case `## Research Context` is the committed source.

## Roadmap Linkage (Optional)

If `.hermes-dev/plans/ROADMAP.md` exists, `aif-plan` may include a `## Roadmap Linkage` section in
the plan file. This makes milestone alignment explicit for `aif-implement` completion marking and
`aif-verify` roadmap gates.

**Example plan file:**

```markdown
# Implementation Plan: User Authentication

Branch: feature/user-authentication
Created: 2026-01-15

## Original Request
Add user authentication with OAuth

## Settings
- Testing: no
- Logging: verbose
- Docs: yes          # aif-implement shows mandatory docs checkpoint, then routes through aif-docs

## Research Context (optional)
Source: .hermes-dev/research/RESEARCH.md (Active Summary, Updated: YYYY-MM-DD HH:MM, SHA256: <active-summary-sha256>)
Goal: Add OAuth + email login
Constraints: Must support existing session middleware
Decisions: Use JWT for API auth
Open questions: Do we need refresh tokens?

## Commit Plan
- **Commit 1** (tasks 1-3): "feat: add user model and types"
- **Commit 2** (tasks 4-6): "feat: implement auth service"

## Tasks

### Phase 1: Setup
- [ ] Task 1: Create User model
- [ ] Task 2: Add auth types

### Phase 2: Implementation
- [x] Task 3: Implement registration
- [ ] Task 4: Implement login
```

## Self-Improvement Patches

The department has a built-in learning loop. Every bug fix creates a **patch** — a structured
knowledge artifact that helps AI avoid the same mistakes in the future.

```
aif-fix → finds bug → fixes it → creates patch → aif-evolve distills new patches into skill-context → smarter future runs
```

**How it works:**

1. `aif-fix` fixes a bug and creates a patch file in `.hermes-dev/patches/YYYY-MM-DD-HH.mm.md`
2. Each patch documents: **Problem**, **Root Cause**, **Solution**, **Prevention**, and **Tags**
3. `aif-evolve` reads patches incrementally using `.hermes-dev/evolution/patch-cursor.json`
   (first run reads all)
4. Workflow skills (`aif-implement`, `aif-fix`, `aif-improve`) prefer skill-context rules and use
   only limited recent patch fallback when needed

**Example patch** (`.hermes-dev/patches/2026-02-07-14.30.md`):

```markdown
# Null reference in UserProfile when user has no avatar

**Date:** 2026-02-07 14:30
**Files:** src/components/UserProfile.tsx
**Severity:** medium

## Problem
TypeError: Cannot read property 'url' of undefined when rendering UserProfile.

## Root Cause
`user.avatar` is optional in DB but accessed without null check.

## Solution
Added optional chaining: `user.avatar?.url` with fallback.

## Prevention
- Always null-check optional DB fields in UI
- Add "empty state" test cases

## Tags
`#null-check` `#react` `#optional-field`
```

The more you use `aif-fix`, the smarter AI becomes on your project. Patches accumulate and create a
project-specific knowledge base.

**Periodic evolution** — run `aif-evolve` to analyze new patches and automatically improve skills:

```
aif-evolve      # Analyze patches + project → improve all skills
```

This closes the full learning loop: **fix → patch → evolve → better skills → fewer bugs → smarter
fixes**.

## Skill Acquisition Strategy

The Hermes adaptation of lee-to's strategy (skills.sh / npx installer machinery is not used):

```
For each recommended skill:
  1. Check ~/.hermes/skills/ (hermes skills list) — does an equivalent already exist?
  2. If a third-party skill is brought in → copy the folder into ~/.hermes/skills/
  3. Security review BEFORE first use → manual two-level checklist (see Security)
     - BLOCKED-class findings? → remove the folder, warn, skip
     - WARNING-class findings? → show them, require explicit confirmation
  4. If nothing suitable exists → generate: aif-skill-generator <name>
  5. Has reference docs? → Learn Mode: aif-skill-generator <url1> [url2]...
  6. Verify visibility: hermes skills list
```

**Never reinvent existing skills** — always check the installed set first. **Never trust external
skills blindly** — always review before use. When reference documentation is available, use
**Learn Mode** to generate skills from real sources.

## See Also

- [Development Workflow](workflow.md) — how plan files fit into the development loop
- [Core Skills](skills.md) — full reference for `aif-fix`, `aif-evolve`, and other skills
- [Security](security.md) — how external skills are reviewed before use
