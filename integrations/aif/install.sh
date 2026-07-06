#!/bin/sh
# AIF (AI Factory) x Hermes integration installer.
#
# Installs the runtime assets that accompany the AIF workflow core:
#   - skills/*    -> $HERMES_HOME/skills/           (30 aif-* skills + dev-handoff)
#   - agents/*    -> $CLAUDE_AGENTS_DIR/            (19 Claude Code subagents)
#   - profiles/*  -> $HERMES_HOME/profiles/<name>/  (5 role profiles, SOUL.md)
# then wires the profiles to the shared skills directory and pins the
# `departments` board to the aif_planner orchestrator.
#
# Idempotent: safe to re-run. Existing skills/agents of the same name are
# replaced with the packaged version; profile config.yaml is MERGED (only
# skills.external_dirs is touched — approvals.mode and everything else is
# preserved).
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CLAUDE_AGENTS_DIR="${CLAUDE_AGENTS_DIR:-$HOME/.claude/agents}"
PROFILES="aif_planner aif_specifier aif_implementer aif_verifier aif_reviewer"

# Pick a python that can import PyYAML for the config merge (step 4). Prefer
# the Hermes venv python — it also carries hermes_cli for step 5. Override
# with HERMES_PYTHON=/path/to/python.
PYBIN=python3
for cand in "${HERMES_PYTHON:-}" \
            "$HERMES_HOME/hermes-agent/venv/bin/python3" \
            python3; do
    [ -n "$cand" ] || continue
    if "$cand" -c "import yaml" >/dev/null 2>&1; then
        PYBIN=$cand
        break
    fi
done

echo "== AIF x Hermes integration installer =="
echo "   package : $HERE"
echo "   hermes  : $HERMES_HOME"
echo "   agents  : $CLAUDE_AGENTS_DIR"
echo

# ---------------------------------------------------------------- 1. skills
echo "[1/5] Installing skills -> $HERMES_HOME/skills/"
mkdir -p "$HERMES_HOME/skills"
skill_count=0
for src in "$HERE"/skills/*/; do
    name=$(basename "$src")
    dest="$HERMES_HOME/skills/$name"
    rm -rf "$dest"
    cp -R "$src" "$dest"
    skill_count=$((skill_count + 1))
done
echo "      $skill_count skills installed."

# -------------------------------------------------------------- 2. subagents
echo "[2/5] Installing subagents -> $CLAUDE_AGENTS_DIR/"
mkdir -p "$CLAUDE_AGENTS_DIR"
agent_count=0
for f in "$HERE"/agents/*.md; do
    cp "$f" "$CLAUDE_AGENTS_DIR/$(basename "$f")"
    agent_count=$((agent_count + 1))
done
echo "      $agent_count subagents installed."

# --------------------------------------------------------------- 3. profiles
echo "[3/5] Creating role profiles (if missing) and installing SOUL.md"
for p in $PROFILES; do
    if [ ! -d "$HERMES_HOME/profiles/$p" ]; then
        if command -v hermes >/dev/null 2>&1; then
            hermes profile create "$p" \
                --description "AIF ${p#aif_} role (AI Factory pipeline)" \
                || mkdir -p "$HERMES_HOME/profiles/$p"
        else
            echo "      [warn] hermes CLI not on PATH — creating bare profile dir for $p"
            mkdir -p "$HERMES_HOME/profiles/$p"
        fi
    fi
    cp "$HERE/profiles/$p/SOUL.md" "$HERMES_HOME/profiles/$p/SOUL.md"
    echo "      $p: SOUL.md installed."
done

# ------------------------------------------- 4. wire shared skills directory
# Each role profile must see the shared skills dir ($HERMES_HOME/skills)
# through skills.external_dirs in its config.yaml. Merge, do not overwrite:
# every other key (including approvals.mode) is preserved. Note: PyYAML
# re-serializes the file, so YAML comments in config.yaml are not preserved.
echo "[4/5] Merging skills.external_dirs into each profile's config.yaml"
for p in $PROFILES; do
    cfg="$HERMES_HOME/profiles/$p/config.yaml"
    if "$PYBIN" - "$cfg" "$HERMES_HOME/skills" <<'PY'
import os
import sys

path, skills_dir = sys.argv[1], sys.argv[2]
try:
    import yaml
except ImportError:
    sys.exit(1)

data = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
if not isinstance(data, dict):
    sys.exit(1)

skills = data.get("skills") or {}
if not isinstance(skills, dict):
    sys.exit(1)
dirs = skills.get("external_dirs") or []
if not isinstance(dirs, list):
    sys.exit(1)

if skills_dir not in dirs:
    dirs.append(skills_dir)
skills["external_dirs"] = dirs
data["skills"] = skills

with open(path, "w", encoding="utf-8") as fh:
    yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
PY
    then
        echo "      $p: skills.external_dirs includes $HERMES_HOME/skills"
    else
        echo "      [warn] $p: could not merge automatically (PyYAML missing or"
        echo "             unexpected config shape). Add this to $cfg manually:"
        echo "               skills:"
        echo "                 external_dirs:"
        echo "                   - \"$HERMES_HOME/skills\""
    fi
done

# --------------------------------------- 5. departments board orchestration
echo "[5/5] Pinning the 'departments' board to the aif_planner orchestrator"
if "$PYBIN" - <<'PY'
from hermes_cli.kanban_db import write_board_metadata

meta = write_board_metadata(
    "departments",
    orchestrator_profile="aif_planner",
    default_assignee="aif_planner",
)
print("      departments board.json: orchestrator_profile=%s default_assignee=%s"
      % (meta.get("orchestrator_profile"), meta.get("default_assignee")))
PY
then
    :
else
    echo "      [warn] could not import hermes_cli — run this manually inside"
    echo "             your Hermes environment (venv/checkout on PYTHONPATH):"
    echo "               python3 -c \"from hermes_cli.kanban_db import write_board_metadata; write_board_metadata('departments', orchestrator_profile='aif_planner', default_assignee='aif_planner')\""
fi

# ------------------------------------------------------------------ summary
echo
echo "== Done. Post-install checklist =="
echo
echo "1. Optional workflow tuning in your Hermes config (cli-config.yaml,"
echo "   'kanban:' section) — defaults in parentheses:"
echo "     kanban.max_review_iterations   review FAIL->rework rounds before"
echo "                                    manual_review_required (3)"
echo "     kanban.auto_review_strategy    convergence strategy:"
echo "                                    full_re_review | closure_first"
echo "     kanban.use_subagents           default delegation mode for workflow"
echo "                                    cards (on)"
echo "     kanban.run_plan_improve        insert the optional 'improve' stage"
echo "                                    after planning"
echo "     kanban.run_post_verify         insert the optional 'verify' stage"
echo "                                    before review"
echo
echo "2. Restart the Hermes gateway so the dispatcher picks up the new"
echo "   profiles and board orchestration."
echo
echo "3. Smoke test:"
echo "     hermes kanban create \"Hello AIF\" --workflow aif"
echo "   and watch the card walk spec -> planning -> implementing -> review."
