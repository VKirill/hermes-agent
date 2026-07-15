"""Kanban decomposer — fan a triage task out into a graph of child tasks.

Invoked by ``hermes kanban decompose [task_id | --all]`` and the
auto-decompose path in the gateway dispatcher loop. Reads the user's
profile roster (with descriptions) and asks the auxiliary LLM to
return a task graph in JSON. Then atomically creates the children,
links them under the root, and flips the root ``triage -> todo``.

The root task stays alive and becomes the parent of every leaf child,
so when the whole graph completes the root wakes back up — its
assignee (the orchestrator profile) gets a chance to judge completion
and add more tasks if the work isn't done yet.

Design notes
------------

* Mirrors the shape of ``hermes_cli/kanban_specify.py``: lazy aux
  client import inside the function, lenient response parse, never
  raises on expected failure modes.

* The system prompt sees the *configured* profile roster — names plus
  descriptions plus the default fallback. Profiles without a
  description are still listed (with a note) so the decomposer can
  match on name as a fallback, but the user has an obvious incentive
  to describe them.

* ``fanout=false`` collapses to the same effect as ``kanban specify``:
  we tighten the body and flip ``triage -> todo`` as a single task,
  no children created. This makes ``decompose`` a strict superset of
  ``specify`` from the user's perspective.

* If the LLM picks an assignee that doesn't exist as a profile, or a
  profile that has been deprecated for new routing, we rewrite it to
  the configured ``default_assignee`` (or the default profile if unset).
  A child task NEVER ends up with ``assignee=None``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from hermes_cli import kanban_db as kb
from hermes_cli import profiles as profiles_mod
from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


def _routing_dir() -> Path:
    return get_hermes_home() / "routing"


def _routing_table_for_board(board_name: str) -> dict | None:
    """Load the deterministic (skill -> profile) routing table for a board.

    Tables live at ``<HERMES_HOME>/routing/*.yaml``; each declares its own
    ``board:`` key so any file whose board matches is used regardless of
    filename. Missing directory, missing file, or a parse error all yield
    ``None`` — decompose_task falls straight back to LLM/config routing,
    exactly as if no table existed. This is deliberately re-read (not
    process-cached) so editing the table takes effect on the next decompose
    without a restart; the file is tiny and decompose already makes a
    network round-trip, so the extra disk read is noise.
    """
    board_name = (board_name or "").strip()
    if not board_name:
        return None
    directory = _routing_dir()
    if not directory.is_dir():
        return None
    try:
        for path in sorted(directory.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.debug("decompose: failed to parse routing table %s: %s", path, exc)
                continue
            if isinstance(data, dict) and (data.get("board") or "").strip() == board_name:
                return data
    except Exception as exc:
        logger.debug("decompose: routing table scan failed: %s", exc)
    return None


def _deterministic_route(
    board_name: str,
    skill: object,
    fallback_assignee: str,
    valid_names: set[str],
    deprecated_assignees: set[str],
) -> tuple[str, str]:
    """Override an LLM-picked assignee with the board's routing table, if any.

    Precedence when a table exists for this board: explicit ``by_skill[skill]``
    entry > table's own ``default`` > whatever the LLM/global config already
    chose (``fallback_assignee``). A mapped profile that doesn't exist or is
    deprecated is ignored (never route to a ghost profile) and resolution
    falls through to the next tier. No table for this board, or no skill on
    this task, leaves ``fallback_assignee`` untouched — this only *narrows*
    routing for boards that opted in, it never breaks boards without a table.

    Returns ``(assignee, tier)`` where ``tier`` is one of ``table_skill``,
    ``table_default``, or ``fallback`` — for routing-decision observability
    (see ``_log_routing_decision``), not used for control flow.
    """
    table = _routing_table_for_board(board_name)
    if not table:
        return fallback_assignee, "fallback"
    by_skill = table.get("by_skill") if isinstance(table.get("by_skill"), dict) else {}
    skill_key = skill.strip() if isinstance(skill, str) else ""
    if skill_key:
        mapped = by_skill.get(skill_key)
        if isinstance(mapped, str) and mapped.strip():
            mapped = mapped.strip()
            if mapped in valid_names and mapped not in deprecated_assignees:
                return mapped, "table_skill"
            logger.info(
                "decompose: routing table maps skill %r -> %r but that profile "
                "is missing/deprecated — falling through", skill_key, mapped,
            )
    default = table.get("default")
    if isinstance(default, str) and default.strip():
        default = default.strip()
        if default in valid_names and default not in deprecated_assignees:
            return default, "table_default"
    return fallback_assignee, "fallback"


def _routing_log_path() -> Path:
    return get_hermes_home() / "kanban" / "routing-decisions.log"


def _log_routing_decision(
    *,
    task_id: str,
    board: str,
    skill: object,
    llm_assignee_raw: object,
    tier: str,
    final_assignee: str,
) -> None:
    """Append one JSONL record of a routing decision for dashboard observability.

    Best-effort only: any failure (missing dir, disk full, permissions) is
    swallowed — this is an observability side-channel, never allowed to
    affect task routing or fail a decompose call. Rotates by truncating to
    the last ``_ROUTING_LOG_MAX_LINES`` once it grows past ~2x that, so the
    file doesn't grow unbounded on a long-lived install.
    """
    try:
        import time

        path = _routing_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.time(),
            "task_id": task_id,
            "board": board,
            "skill": skill if isinstance(skill, str) else None,
            "llm_assignee_raw": llm_assignee_raw if isinstance(llm_assignee_raw, str) else None,
            "tier": tier,
            "final_assignee": final_assignee,
        }
        line = json.dumps(record, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _maybe_rotate_routing_log(path)
    except Exception as exc:
        logger.debug("decompose: routing-decision log write failed: %s", exc)


_ROUTING_LOG_MAX_LINES = 2000


def _maybe_rotate_routing_log(path: Path) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= _ROUTING_LOG_MAX_LINES * 2:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines[-_ROUTING_LOG_MAX_LINES:])
    except Exception as exc:
        logger.debug("decompose: routing-decision log rotate failed: %s", exc)


# Legacy development profile names that must not receive new kanban work.
# Keep this intentionally small and role-specific: generic deprecated routing
# aliases can still live in profile inventory docs, but the decomposer must not
# expose obsolete development lanes to the LLM roster or accept them as valid
# assignees when they are replaced by native Hermes/AIF profiles.
_DEFAULT_DEPRECATED_ASSIGNEES = frozenset({
    "dev_factory",
    "dev-factory",
    "devfactory",
    "backendgpu",
    "backend_gpu",
    "systemdev",
})


_SYSTEM_PROMPT = """You are the Kanban decomposer for the Hermes Agent board.

A user dropped a rough idea into the Triage column. Your job is to break it
into a small graph of concrete child tasks and route each one to the best-
matching profile from the available roster.

You will be given:
  - The original task title and body
  - The list of available profiles (each with name + description)
  - The fallback "default_assignee" used when no profile fits

Output a single JSON object with this exact shape:

  {
    "fanout": true,
    "rationale": "<one sentence on why this decomposition>",
    "tasks": [
      {
        "title": "<concrete task title, imperative voice, <= 80 chars>",
        "body":  "<detailed spec for the worker on this child task>",
        "assignee": "<profile name from the roster, or null for default>",
        "skill": "<short skill/capability slug this task needs, e.g. 'direct-ads-copy', 'seo-copywriting', 'ga4-data-api', or null if none is obvious>",
        "parents": [<int>, ...]
      },
      ...
    ]
  }

Rules:
  - "parents" is a list of INDICES (0-based) into this same "tasks" list,
    expressing actual data dependencies. Tasks with no parents run in
    PARALLEL. Tasks with parents wait until every parent completes.
  - Prefer parallelism. If two tasks can be done independently, give
    them no parents so the dispatcher fans them out at once.
  - Use 2-6 tasks for normal work. Don't create 20 tiny tasks. Don't
    cram everything into 1 task.
  - Pick assignees from the roster by matching the task to the profile's
    DESCRIPTION (not just the name). When nothing matches well, use null
    and the system will route to the default_assignee.
  - "skill" is your best guess at the named capability/skill this task
    exercises (a short kebab-case slug), independent of "assignee". Some
    boards use it to deterministically override routing — get it right even
    if you're unsure of the exact assignee. Use null if nothing fits.
  - Each child task body is what a fresh worker will read with no other
    context — be specific about goal, approach, and acceptance criteria.

When the task is genuinely a single unit of work (no useful decomposition),
return:

  {
    "fanout": false,
    "rationale": "<one sentence>",
    "title": "<tightened title>",
    "body":  "<concrete spec for a single worker>",
    "assignee": "<profile name from the roster, or null for default>",
    "skill": "<short skill/capability slug this task needs, or null>"
  }

In that case the task stays as one work item, just with a tightened spec and
a concrete assignee. If no profile fits, use null and the system will route to
the default_assignee.

No preamble, no closing remarks, no code fences. Output only the JSON object.
"""


_USER_TEMPLATE = """Task id: {task_id}
Title: {title}
Body:
{body}

Available profiles (assignees you may pick from):
{roster}

Default assignee (used when no profile fits a task): {default_assignee}
"""


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass
class DecomposeOutcome:
    """Result of decomposing a single triage task."""

    task_id: str
    ok: bool
    reason: str = ""
    fanout: bool = False
    child_ids: list[str] | None = None
    new_title: Optional[str] = None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _extract_json_blob(raw: str) -> Optional[dict]:
    if not raw:
        return None
    stripped = _FENCE_RE.sub("", raw.strip())
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    candidate = stripped[first : last + 1]
    try:
        val = json.loads(candidate)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(val, dict):
        return None
    return val


def _profile_author() -> str:
    """Mirror of ``hermes_cli.kanban._profile_author``."""
    return (
        os.environ.get("HERMES_PROFILE")
        or os.environ.get("USER")
        or "decomposer"
    )


def _load_config() -> dict:
    try:
        from hermes_cli.config import load_config
        return load_config() or {}
    except Exception:
        return {}


def _deprecated_assignees_from_config(cfg: dict) -> set[str]:
    """Return profile names that should not be used for NEW routing.

    ``kanban.deprecated_assignees`` is the canonical key. The legacy-friendly
    alias ``kanban.deprecated_profiles`` is accepted because operators tend to
    describe this as "deprecated profiles" in maintenance notes.
    """
    deprecated = set(_DEFAULT_DEPRECATED_ASSIGNEES)
    kanban_cfg = cfg.get("kanban", {}) if isinstance(cfg, dict) else {}
    for key in ("deprecated_assignees", "deprecated_profiles"):
        raw = kanban_cfg.get(key)
        if isinstance(raw, str):
            values = [part.strip() for part in raw.split(",")]
        elif isinstance(raw, (list, tuple, set)):
            values = [str(part).strip() for part in raw]
        else:
            values = []
        deprecated.update(value for value in values if value)
    return deprecated


def _profile_exists_and_not_deprecated(name: str, deprecated_assignees: set[str]) -> bool:
    if not name or name in deprecated_assignees:
        return False
    try:
        return profiles_mod.profile_exists(name)
    except Exception:
        return False


def _first_non_deprecated_profile(deprecated_assignees: set[str]) -> Optional[str]:
    try:
        all_profiles = profiles_mod.list_profiles()
    except Exception:
        return None
    for p in all_profiles:
        name = getattr(p, "name", "")
        if name and name not in deprecated_assignees:
            return name
    return None


def _resolve_orchestrator_profile(
    cfg: dict,
    deprecated_assignees: set[str] | None = None,
    board_override: str | None = None,
    routing_orchestrator: str | None = None,
) -> str:
    """Resolve which profile owns the root/orchestration task after fan-out.

    Precedence: per-board ``board.json`` override → this board's deterministic
    routing table (``routing/*.yaml``'s ``orchestrator:`` key, if any) → global
    ``kanban.orchestrator_profile`` → the active default profile (so a task
    is never stranded for lack of an orchestrator). The per-board override
    lets a dev board be led by a dev profile while the marketing board keeps
    its own lead; the routing table sits one tier below it so a manual
    ``board.json`` edit still wins if someone sets one.
    """
    deprecated_assignees = deprecated_assignees or set()
    board_override = (board_override or "").strip()
    if board_override and _profile_exists_and_not_deprecated(board_override, deprecated_assignees):
        return board_override
    routing_orchestrator = (routing_orchestrator or "").strip()
    if routing_orchestrator and _profile_exists_and_not_deprecated(routing_orchestrator, deprecated_assignees):
        return routing_orchestrator
    kanban_cfg = cfg.get("kanban", {}) if isinstance(cfg, dict) else {}
    explicit = (kanban_cfg.get("orchestrator_profile") or "").strip()
    if explicit and _profile_exists_and_not_deprecated(explicit, deprecated_assignees):
        return explicit
    # Fall back to the active default profile.
    try:
        active = profiles_mod.get_active_profile_name() or "default"
    except Exception:
        active = "default"
    if active not in deprecated_assignees:
        return active
    return _first_non_deprecated_profile(deprecated_assignees) or active


def _resolve_default_assignee(
    cfg: dict,
    deprecated_assignees: set[str] | None = None,
    board_override: str | None = None,
) -> str:
    """Resolve which profile catches child tasks the orchestrator can't route.

    Precedence: per-board ``board.json`` override → global
    ``kanban.default_assignee`` → the active default profile.
    """
    deprecated_assignees = deprecated_assignees or set()
    board_override = (board_override or "").strip()
    if board_override and _profile_exists_and_not_deprecated(board_override, deprecated_assignees):
        return board_override
    kanban_cfg = cfg.get("kanban", {}) if isinstance(cfg, dict) else {}
    explicit = (kanban_cfg.get("default_assignee") or "").strip()
    if explicit and _profile_exists_and_not_deprecated(explicit, deprecated_assignees):
        return explicit
    try:
        active = profiles_mod.get_active_profile_name() or "default"
    except Exception:
        active = "default"
    if active not in deprecated_assignees:
        return active
    return _first_non_deprecated_profile(deprecated_assignees) or active


def _build_roster(deprecated_assignees: set[str] | None = None) -> tuple[list[dict], set[str]]:
    """Return (roster_for_prompt, valid_assignee_names).

    Each roster entry is ``{name, description, has_description}``. The
    valid-set is used after the LLM responds to rewrite invalid
    assignees to the default fallback. Deprecated profile names are
    intentionally omitted from both values so the LLM is not invited to
    choose them and cannot sneak them back as valid assignees.
    """
    deprecated_assignees = deprecated_assignees or set()
    roster: list[dict] = []
    valid: set[str] = set()
    try:
        all_profiles = profiles_mod.list_profiles()
    except Exception as exc:
        logger.warning("decompose: failed to list profiles: %s", exc)
        return roster, valid
    for p in all_profiles:
        if p.name in deprecated_assignees:
            continue
        desc = (p.description or "").strip()
        roster.append({
            "name": p.name,
            "description": desc or f"(no description; profile named {p.name!r})",
            "has_description": bool(desc),
        })
        valid.add(p.name)
    return roster, valid


def _format_roster(roster: list[dict]) -> str:
    if not roster:
        return "  (no profiles installed — decomposer cannot route work)"
    lines = []
    for entry in roster:
        tag = "" if entry["has_description"] else " ⚠ undescribed"
        lines.append(f"  - {entry['name']}{tag}: {entry['description']}")
    return "\n".join(lines)


def _normalize_assignee_choice(
    assignee: object,
    *,
    default_assignee: str,
    valid_names: set[str],
) -> str:
    """Return a valid assignee, falling back to ``default_assignee``.

    Fan-out children and the single-task fallback should share the same
    routing guarantee: promoted work must not be left unassigned.
    """
    if not isinstance(assignee, str) or not assignee.strip():
        return default_assignee
    chosen = assignee.strip()
    if chosen not in valid_names:
        return default_assignee
    return chosen


def _current_board_metadata() -> dict:
    """Return the current board's ``board.json`` for per-board orchestration
    overrides (``orchestrator_profile`` / ``default_assignee``).

    The current board is resolved from ``HERMES_KANBAN_BOARD`` (the dispatcher
    pins it per tick). Never raises — a missing/malformed file yields ``{}`` so
    resolution falls through to the global config.
    """
    try:
        return kb.read_board_metadata(kb.get_current_board()) or {}
    except Exception:
        return {}


def decompose_task(
    task_id: str,
    *,
    author: Optional[str] = None,
    timeout: Optional[int] = None,
) -> DecomposeOutcome:
    """Decompose a triage task into a graph of child tasks.

    Returns an outcome describing what happened. Never raises for
    expected failure modes (task not in triage, no aux client
    configured, API error, malformed response, decomposer returned
    fanout=true with empty task list) — those surface via ``ok=False``.
    """
    with kb.connect_closing() as conn:
        task = kb.get_task(conn, task_id)
    if task is None:
        return DecomposeOutcome(task_id, False, "unknown task id")
    if task.status != "triage":
        return DecomposeOutcome(
            task_id, False, f"task is not in triage (status={task.status!r})"
        )

    cfg = _load_config()
    deprecated_assignees = _deprecated_assignees_from_config(cfg)
    board_meta = _current_board_metadata()
    board_name = kb.get_current_board()
    routing_table = _routing_table_for_board(board_name)
    orchestrator = _resolve_orchestrator_profile(
        cfg, deprecated_assignees,
        (board_meta.get("orchestrator_profile") or "").strip(),
        (routing_table or {}).get("orchestrator"),
    )
    default_assignee = _resolve_default_assignee(
        cfg, deprecated_assignees,
        (board_meta.get("default_assignee") or "").strip(),
    )
    kanban_cfg = cfg.get("kanban", {}) if isinstance(cfg, dict) else {}
    auto_promote = bool(kanban_cfg.get("auto_promote_children", True))
    roster, valid_names = _build_roster(deprecated_assignees)

    try:
        from agent.auxiliary_client import call_llm  # type: ignore
    except Exception as exc:
        logger.debug("decompose: auxiliary client import failed: %s", exc)
        return DecomposeOutcome(task_id, False, "auxiliary client unavailable")

    user_msg = _USER_TEMPLATE.format(
        task_id=task.id,
        title=_truncate(task.title or "", 400),
        body=_truncate(task.body or "(no body)", 4000),
        roster=_format_roster(roster),
        default_assignee=default_assignee,
    )

    try:
        # Route through call_llm so auxiliary.kanban_decomposer.* config
        # (provider/model/base_url, extra_body, reasoning_effort, retries)
        # all apply — the previous direct client.chat.completions.create()
        # path dropped auxiliary.<task>.extra_body entirely (#35566).
        resp = call_llm(
            task="kanban_decomposer",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            max_tokens=4000,
            timeout=timeout or 180,
        )
    except Exception as exc:
        logger.info(
            "decompose: API call failed for %s (%s)", task_id, exc,
        )
        return DecomposeOutcome(task_id, False, f"LLM error: {type(exc).__name__}")

    try:
        raw = resp.choices[0].message.content or ""
    except Exception:
        raw = ""

    parsed = _extract_json_blob(raw)
    if parsed is None:
        return DecomposeOutcome(task_id, False, "LLM returned malformed JSON")

    fanout = bool(parsed.get("fanout"))
    audit_author = author or _profile_author()

    if not fanout:
        # Fall back to single-task spec promotion (same effect as specify).
        new_title = parsed.get("title")
        new_body = parsed.get("body")
        title_val = new_title.strip() if isinstance(new_title, str) and new_title.strip() else None
        body_val = new_body if isinstance(new_body, str) and new_body.strip() else None
        assignee_val = None
        if not task.assignee:
            assignee_val = _normalize_assignee_choice(
                parsed.get("assignee"),
                default_assignee=default_assignee,
                valid_names=valid_names,
            )
            assignee_val, _tier = _deterministic_route(
                board_name, parsed.get("skill"), assignee_val,
                valid_names, deprecated_assignees,
            )
            _log_routing_decision(
                task_id=task_id, board=board_name, skill=parsed.get("skill"),
                llm_assignee_raw=parsed.get("assignee"), tier=_tier,
                final_assignee=assignee_val,
            )
        if title_val is None and body_val is None:
            return DecomposeOutcome(
                task_id, False, "decomposer returned fanout=false with no title/body",
            )
        with kb.connect_closing() as conn:
            ok = kb.specify_triage_task(
                conn,
                task_id,
                title=title_val,
                body=body_val,
                assignee=assignee_val,
                author=audit_author,
            )
        if not ok:
            return DecomposeOutcome(
                task_id, False, "task moved out of triage before promotion",
            )
        return DecomposeOutcome(
            task_id, True, "single task (no fanout)",
            fanout=False, new_title=title_val,
        )

    raw_tasks = parsed.get("tasks") or []
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return DecomposeOutcome(
            task_id, False, "decomposer returned fanout=true with empty tasks list",
        )

    # Rewrite invalid assignees to the default fallback. Never leave a
    # task with assignee=None — the user explicitly does not want that.
    children: list[dict] = []
    for idx, entry in enumerate(raw_tasks):
        if not isinstance(entry, dict):
            return DecomposeOutcome(
                task_id, False, f"tasks[{idx}] is not an object",
            )
        title = entry.get("title")
        if not isinstance(title, str) or not title.strip():
            return DecomposeOutcome(
                task_id, False, f"tasks[{idx}].title is missing or empty",
            )
        body = entry.get("body")
        if not isinstance(body, str):
            body = ""
        assignee = entry.get("assignee")
        chosen = _normalize_assignee_choice(
            assignee,
            default_assignee=default_assignee,
            valid_names=valid_names,
        )
        if (
            isinstance(assignee, str)
            and assignee.strip()
            and assignee.strip() not in valid_names
        ):
            logger.info(
                "decompose: task %s child %d picked unknown assignee %r — "
                "routing to default_assignee %r",
                task_id, idx, assignee, default_assignee,
            )
        chosen, _tier = _deterministic_route(
            board_name, entry.get("skill"), chosen, valid_names, deprecated_assignees,
        )
        _log_routing_decision(
            task_id=f"{task_id}#{idx}", board=board_name, skill=entry.get("skill"),
            llm_assignee_raw=assignee, tier=_tier, final_assignee=chosen,
        )
        parents = entry.get("parents") or []
        if not isinstance(parents, list):
            parents = []
        # Clean parent indices: drop non-int and out-of-range.
        clean_parents = [p for p in parents if isinstance(p, int) and 0 <= p < len(raw_tasks) and p != idx]
        children.append({
            "title": title.strip()[:200],
            "body": body.strip(),
            "assignee": chosen,
            "parents": clean_parents,
        })

    try:
        with kb.connect_closing() as conn:
            child_ids = kb.decompose_triage_task(
                conn,
                task_id,
                root_assignee=orchestrator,
                children=children,
                author=audit_author,
                auto_promote=auto_promote,
            )
    except ValueError as exc:
        return DecomposeOutcome(task_id, False, f"DB rejected graph: {exc}")
    except Exception as exc:
        logger.exception("decompose: DB error on task %s", task_id)
        return DecomposeOutcome(task_id, False, f"DB error: {type(exc).__name__}")

    if child_ids is None:
        return DecomposeOutcome(
            task_id, False, "task moved out of triage before decomposition",
        )

    return DecomposeOutcome(
        task_id, True, f"decomposed into {len(child_ids)} children",
        fanout=True, child_ids=child_ids,
    )


def list_triage_ids(*, tenant: Optional[str] = None) -> list[str]:
    """Return task ids currently in the triage column."""
    with kb.connect_closing() as conn:
        rows = kb.list_tasks(
            conn,
            status="triage",
            tenant=tenant,
            limit=1000,
        )
    return [row.id for row in rows]
