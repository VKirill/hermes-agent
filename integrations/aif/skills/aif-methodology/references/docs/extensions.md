[← Security](security.md) · [AIF methodology](../../SKILL.md) · [Configuration →](configuration.md)

> Concept port of lee-to AI Factory `docs/extensions.md`. The extension machinery
> (`extension.json` manifest, `extension.schema.json`, `ai-factory extension add/update/remove`,
> injection markers, managed-file tracking) is **not wired in Hermes**. This page keeps the
> concept map and documents how each extension capability is achieved here instead.

# Extensions

In lee-to, extensions let third-party developers add capabilities to AI Factory — custom CLI
commands, MCP servers, skill injections, runtime definitions, runtime-specific agent files — all
declared in an `extension.json` manifest, validated against a published JSON schema, installed
into `.ai-factory/extensions/<name>/`, tracked in `.ai-factory.json`, and automatically re-applied
after `ai-factory update`.

**None of that machinery exists in Hermes.** There is no installer to survive, no per-project
skills copy to re-inject into, and no manifest schema. Third-party additions are made directly:
skills are added to `~/.hermes/skills/` and validated by `hermes skills list`.

## Capability map: lee-to extension features → Hermes

| lee-to extension capability | Hermes way |
|-----------------------------|------------|
| `skills` — bundle custom skills | Copy the skill folder into `~/.hermes/skills/<name>/`; verify with `hermes skills list`. **Security-review it first** (see [Security](security.md)) |
| `replaces` — replace a built-in skill under its base name | Edit or replace the skill folder in `~/.hermes/skills/` directly. Record the deviation in the parity matrix so a future refresh of the port does not silently revert it |
| `injections` — append/prepend content into existing skill files | Two options: **project-scoped** rules go to `.hermes-dev/skill-context/<skill>/SKILL.md` (higher priority than the base skill, survives refreshes — the preferred mechanism, see [Skill Evolution](evolve.md)); **global** changes are direct edits to `~/.hermes/skills/<skill>/SKILL.md` |
| `commands` — custom CLI commands (Commander.js modules) | n/a — there is no plugin CLI. Recurring operations become skills (optionally with `scripts/` inside the skill folder) or Hermes CLI features |
| `mcpServers` — MCP server templates merged into agent settings | Hermes MCP configuration at the gateway level (one place, all workers) — not per project |
| `agents` — new runtime definitions | n/a — Hermes runs one runtime; other models go through Hermes model routing (`model.default`, per-profile overrides) |
| `agentFiles` — runtime-specific subagent files | Drop the `.md` agent file into `~/.claude/agents/` (global). Filename collisions with the 19 bundled agents are yours to avoid — there is no ownership registry |
| version tracking / `extension update` | n/a — folders in `~/.hermes/skills/` are updated manually (git checkout / re-copy). The parity matrix is the inventory of what is installed and why |

## What this trade-off means

lee-to's machinery solves two real problems: **update survival** (base skills are overwritten by
`ai-factory update`, so third-party changes must be re-applied automatically) and **multi-runtime
distribution** (the same extension installs into `.claude/`, `.codex/`, `.cursor/`, …).

Hermes has neither problem in the same form:

- Skills are global and not auto-overwritten — there is no update process that would clobber a
  local edit without a human doing it. The cost: refreshing the port against upstream lee-to is a
  manual, parity-matrix-driven exercise, and local deviations must be recorded there.
- There is one runtime, so runtime adapters and per-runtime agent files are dead weight.

What is genuinely lost and accepted:
- **Idempotent injection markers** (`<!-- aif-ext:...:start/end -->`) — with direct edits there is
  no automatic "strip exactly what the extension added" removal. Mitigation: prefer
  `skill-context` for project-scoped additions (deleting the file cleanly removes them).
- **Manifest validation** (`extension.schema.json`) — nothing validates a third-party skill's
  shape beyond `hermes skills list` picking it up and the manual security review.
- **Rollback on remove** (base skill restored when a replacement is removed) — keep the original
  folder (e.g. a `.bak` copy or git history) before replacing a built-in skill.

## Adding a third-party skill (the Hermes procedure)

```
1. Obtain the skill folder (git clone / download).
2. Security review — mandatory two-level check BEFORE first use (see Security):
   deterministic pattern sweep + LLM semantic review.
   Any CRITICAL finding → do not install, delete the folder.
3. Copy to ~/.hermes/skills/<name>/ .
4. Verify: hermes skills list   (the skill must appear; fix frontmatter if not).
5. If it replaces or modifies a built-in aif-* skill — record the deviation in parity-matrix.md.
6. Project-specific tuning → .hermes-dev/skill-context/<name>/SKILL.md, not base-file edits.
```

## Security Considerations (retained from lee-to, adapted)

- **Review before install** — external skills can carry prompt injection; the two-level review in
  [Security](security.md) is mandatory. lee-to's path-traversal name validation and
  registered-extensions-only loading are replaced by the fact that only folders you deliberately
  place in `~/.hermes/skills/` are ever loaded.
- **Skills execute code** — a skill's `scripts/` run with the worker's permissions. Only install
  skills you trust, just as you would with npm packages.
- **No silent additions** — nothing auto-installs skills; every folder in `~/.hermes/skills/` was
  placed there by a human or an explicitly-approved task.

## Community extensions (lee-to ecosystem)

lee-to's community extensions can still be useful as **source material**: their `skills/` folders
port the same way any third-party skill does (review → copy → verify), and their injections can be
re-expressed as skill-context rules. Known ones at port time:

| Extension | What it adds | Hermes take |
|-----------|--------------|-------------|
| Remote Skills | install/manage skills from GitHub repos | superseded by the manual procedure above |
| AIF Extension Creator | interactive scaffolding of new extensions | n/a — use `aif-skill-generator` to scaffold skills instead |
| Implementation Notes | append-only decision journal for `aif-implement`, feeds `aif-commit` bodies, WARN-only coverage gate in `aif-verify` | portable as a skill + skill-context additions if wanted |

## See Also

- [Configuration](configuration.md) — where configuration actually lives in Hermes
- [Core Skills](skills.md) — all built-in skills
- [Security](security.md) — two-level review for external skills
- [Skill Evolution](evolve.md) — skill-context, the preferred injection mechanism
