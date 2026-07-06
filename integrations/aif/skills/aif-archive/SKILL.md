---
name: aif-archive
description: >-
  Archive completed plans and roadmap milestones: move finished plans from
  .hermes-dev/plans/ into .hermes-dev/archive/plans/ and optionally trim closed
  milestones from .hermes-dev/plans/ROADMAP.md into dated snapshots under
  .hermes-dev/archive/roadmap/. Use when the user says "archive plans",
  "clean up plans", "archive completed", "trim roadmap", or a kanban
  maintenance task asks for plan/artifact cleanup. Port of lee-to AI Factory
  /aif-archive, adapted to Hermes.
tags:
  - aif
  - archive
  - workflow
  - dev-factory
---

# aif-archive — Move completed plans and roadmap snapshots

Archive completed plans from `.hermes-dev/plans/` into `.hermes-dev/archive/plans/` and
optionally trim closed milestones from `.hermes-dev/plans/ROADMAP.md` into dated snapshots
under `.hermes-dev/archive/roadmap/`.

## Hermes context

- Artifacts live under **`.hermes-dev/`** in the target workspace (apps live at `~/Work/apps/<slug>/`).
  There is **no `.ai-factory/config.yaml`** — paths are fixed (see Step 0). Department conventions: `aif-methodology`.
- **Autonomy:** as a kanban worker you have no human at the keyboard. Where the original asked for
  confirmation (interactive/`--all`/`--roadmap`), proceed on evidence — archiving is a reversible `mv`
  and the roadmap trim happens only after the snapshot is safely written. In interactive (topic/CLI)
  sessions you MAY still ask before batch operations. Block the kanban task only for real reasons
  (workspace missing, ambiguous plan name with multiple matches you cannot resolve).
- When running as a worker, finish with `kanban_complete` and a summary (archived N, skipped K,
  remaining M); read the task body via `hermes kanban --board departments show <id>` first.

## Workflow

### Step 0: Resolve paths & load context

Fixed Hermes paths (no config file):

- Plans: `.hermes-dev/plans/`
- Archive: `.hermes-dev/archive/` (plans → `archive/plans/`, roadmap snapshots → `archive/roadmap/`)
- Fix plan: `.hermes-dev/fixes/FIX_PLAN.md`
- Roadmap: `.hermes-dev/plans/ROADMAP.md`

Plan filenames follow the Hermes `aif-plan` convention `<slug>.md`; legacy sequential names
(`NNNN_slug.md`) are handled identically — the completion logic below does not depend on the naming scheme.

Read `.hermes-dev/skill-context/aif-archive/SKILL.md` if it exists — project-specific overrides
(accumulated by `aif-evolve`) take priority over the general instructions in this file.

### Step 1: Parse Arguments

Extract mode from the arguments (or the kanban task body):

```
(no args)        → scan, show completable plans, archive them (worker: all; interactive: may ask which)
list             → show archive contents, then STOP
--roadmap        → trim closed milestones from ROADMAP.md into a snapshot
--all            → archive ALL completed plans
<plan-name>      → archive a specific plan by filename or partial stem match
```

Parsing rules:

- `list` and `--roadmap` are mutually exclusive with `<plan-name>` and `--all`
- If multiple conflicting modes are given, emit error and STOP
- `<plan-name>` can be:
  - full filename: `feature-auth.md` (or legacy `0005_feature-auth.md`)
  - stem without extension: `feature-auth`
  - partial match: `auth` (must match exactly one plan)

### Step 2: Execute Mode

---

#### Mode: Default (no arguments)

1. Scan `.hermes-dev/plans/` for all `*.md` files using `Glob`.
2. For each plan file, read the `## Tasks` section.
3. Determine completion: a plan is **completed** when ALL task checkboxes
   are `- [x]`. Plans with any `- [ ]` are incomplete.
4. If no completed plans found:
   ```
   No completed plans found in .hermes-dev/plans/.
   ```
   → STOP.
5. Display completed plans:
   ```
   Completed plans ready to archive:

     1. feature-alpha.md (completed 2026-05-20)
     2. feature-gamma.md (completed 2026-05-24)

   Incomplete plans (skipped):
     - feature-delta.md (3/7 tasks done)
   ```
6. Select which to archive:
   - **Interactive session:** you may ask (all / specific / cancel).
   - **Kanban worker:** archive all completed plans listed — do not stall waiting for a human.
7. Execute archive operation for selected plans (see **Archive Operation**).

---

#### Mode: `list`

1. Check if `.hermes-dev/archive/plans/` exists.
2. If not: `Archive is empty. No plans have been archived yet.` → STOP.
3. Glob `.hermes-dev/archive/plans/*.md`.
4. For each archived plan, read the YAML frontmatter to extract `archived` date.
5. Display:
   ```
   Archived plans (.hermes-dev/archive/plans/):

     1. feature-alpha.md  (archived: 2026-05-20)
     2. feature-gamma.md  (archived: 2026-05-24)

   Total: 2 archived plans
   ```
6. Check `.hermes-dev/archive/roadmap/` for snapshots and list them if present:
   ```
   Roadmap snapshots (.hermes-dev/archive/roadmap/):

     1. 2026-05-20_roadmap-snapshot.md (3 milestones)
   ```
7. STOP. This mode is strictly read-only — no Write, no Edit, no mv.

---

#### Mode: `<plan-name>`

1. Resolve `<plan-name>` to a file in `.hermes-dev/plans/`:
   - Try exact filename match first
   - Then try with `.md` extension appended
   - Then try partial stem match (grep for `<plan-name>` in filenames)
2. If no match: `Plan not found: <plan-name>` with suggestions → STOP.
3. If multiple matches: list them; interactive — ask the user to be more specific;
   worker — block the kanban task naming the ambiguous candidates → STOP.
4. Read the matched plan file and check completion status.
5. If incomplete:
   ```
   Plan <filename> is not completed (5/8 tasks done).
   Only completed plans can be archived.
   ```
   → STOP.
6. Execute archive operation (see **Archive Operation**).

---

#### Mode: `--all`

1. Scan `.hermes-dev/plans/` for completed plans (same logic as default mode).
2. If no completed plans: inform and STOP.
3. Display the list. Interactive — confirm before proceeding; worker — proceed
   (reversible batch `mv`, no confirmation gate).
4. Execute archive operation for all completed plans.

---

#### Mode: `--roadmap`

1. Read `.hermes-dev/plans/ROADMAP.md`.
2. If it doesn't exist: `No ROADMAP.md found at .hermes-dev/plans/ROADMAP.md.` → STOP.
3. Find milestones with `- [x]` checkbox (completed milestones).
4. If no completed milestones: `No closed milestones to archive.` → STOP.
5. Display what will be trimmed:
   ```
   Closed milestones found in ROADMAP.md:

     - [x] MVP Launch — core features shipped
     - [x] Beta Testing — user feedback round
   ```
   Interactive — confirm before trimming; worker — proceed (the trim only happens after the
   snapshot write succeeds, and the file is under git).
6. Create snapshot:
   - `mkdir -p .hermes-dev/archive/roadmap/`
   - Determine snapshot filename: `YYYY-MM-DD_roadmap-snapshot.md`
   - **Collision check.** Before writing, verify the destination does not already exist:
     ```
     Read .hermes-dev/archive/roadmap/YYYY-MM-DD_roadmap-snapshot.md
     ```
     If the file exists, append a counter suffix to produce a non-colliding name:
     `YYYY-MM-DD_roadmap-snapshot-2.md`, `YYYY-MM-DD_roadmap-snapshot-3.md`, etc.
     Check each candidate until a free name is found.
   - Write the resolved snapshot path with:
     ```markdown
     # Roadmap Snapshot — YYYY-MM-DD

     Archived from: .hermes-dev/plans/ROADMAP.md

     ## Archived Milestones

     - [x] MVP Launch — core features shipped
     - [x] Beta Testing — user feedback round
     ```
7. Edit `.hermes-dev/plans/ROADMAP.md`: remove the archived `- [x]` lines from the
   `## Milestones` section. Keep the `## Completed` table if it exists.
   **Do NOT edit ROADMAP.md unless the snapshot write in step 6 succeeded.**
8. Logging: `INFO [aif-archive] roadmap snapshot: <resolved-path> (<N> milestones archived)`

---

### Archive Operation (plans)

For each plan to archive:

1. `mkdir -p .hermes-dev/archive/plans/`

2. **Collision check.** Before moving, verify the destination does not already exist:
   ```
   Read .hermes-dev/archive/plans/<original-filename>
   ```
   If the file exists:
   - **Single plan** (default or `<plan-name>`): STOP with an error:
     ```
     ERROR [aif-archive] destination already exists: .hermes-dev/archive/plans/<filename>
     A previously archived plan has the same filename. This can happen when
     a reused slug (or sequential numbering) produces a name that was already
     archived. To resolve: rename the existing archive file, or delete it if
     it is no longer needed.
     ```
   - **Batch** (`--all` / worker default): SKIP this plan with a warning, continue to the next:
     ```
     WARN [aif-archive] skipped: <filename> — destination already exists
     ```
   Do NOT overwrite in either case.

3. **Move the source file** into the archive path first:
   ```bash
   mv .hermes-dev/plans/<filename> .hermes-dev/archive/plans/<filename>
   ```
   This atomically removes the plan from the active directory.

4. **Add archive metadata** to the moved file using `Edit`:

   If the file already has YAML frontmatter (between `---` markers at the top):
   - Use `Edit` to add `archived: YYYY-MM-DD` field inside the existing frontmatter block.

   If the file has no YAML frontmatter:
   - Use `Edit` to prepend a minimal frontmatter block before the first line:
     ```yaml
     ---
     archived: YYYY-MM-DD
     ---
     ```

   The original filename is preserved exactly, including any legacy sequential `NNNN_` prefix.

5. Logging: `INFO [aif-archive] archived: <filename> -> .hermes-dev/archive/plans/<filename>`

6. After all plans are processed, display summary:
   ```
   ## Archive Complete

   Archived N plan(s) to .hermes-dev/archive/plans/:
     - feature-alpha.md
     - feature-gamma.md

   Skipped: K (destination already exists)
     - feature-beta.md

   Plans directory: .hermes-dev/plans/ (M plans remaining)
   ```
   Omit the "Skipped" section when K is 0. As a kanban worker, return this summary
   in the `kanban_complete` handoff.

### Completion Detection Algorithm

A plan is **completed** when:

1. The file contains a `## Tasks` section (case-insensitive header match).
2. ALL lines matching the pattern `- [x]` or `- [ ]` within the Tasks section
   (and its subsections) are checked: every checkbox is `- [x]`.
3. If the Tasks section contains zero checkboxes, the plan is considered
   **not completed** (empty plans are not archivable).

Edge cases:

- Checkboxes outside `## Tasks` (e.g., in `## Settings` or `## Commit Plan`)
  are NOT counted for completion.
- Nested checkboxes (indented `  - [x]`) ARE counted.
- Plans without a `## Tasks` section are not archivable — emit
  `WARN [aif-archive] <filename> has no ## Tasks section; skipping`.

### Completion Date Inference

When displaying "completed" dates:

1. Check YAML frontmatter for a `completed` field — use if present.
2. Fall back to git: `git log -1 --format=%ai -- <plan-file>` to get last
   modification date.
3. Fall back to filesystem: file modification time.

## Important Rules

1. **Never archive incomplete plans** — all tasks must be `- [x]`
2. **Never overwrite on collision** — skip (batch) or stop (single); the archive is append-only
3. **Preserve original filenames** — including any legacy sequential `NNNN_` prefix
4. **Add archive metadata** — `archived: YYYY-MM-DD` in YAML frontmatter
5. **Do not modify fix plans** (`.hermes-dev/fixes/FIX_PLAN.md`) —
   that is a single-file artifact managed by `aif-fix`
6. **Do not count archived plans when numbering/naming new plans** — archived plans
   live in `.hermes-dev/archive/plans/`, not `.hermes-dev/plans/`, so `aif-plan`
   never scans them for slug or sequence collisions

## Artifact Ownership

- **Owns:** `.hermes-dev/archive/plans/*.md`, `.hermes-dev/archive/roadmap/*.md`
- **Reads:** `.hermes-dev/plans/*.md`, `.hermes-dev/plans/ROADMAP.md`
- **Modifies:** `.hermes-dev/plans/ROADMAP.md` (only with `--roadmap`, only after the snapshot is written)
- **Does NOT touch:** `.hermes-dev/fixes/FIX_PLAN.md`, `DESCRIPTION.md`,
  `ARCHITECTURE.md`, `.hermes-dev/RULES.md`
