"""Machine-readable Kanban developer gate-result contract.

Developer agents can attach a ``gate_result`` verdict to ``kanban_complete``
metadata.  The validator is deliberately small and stdlib-only because this
path runs inside the agent tool surface: malformed verdicts fail closed before
the task is marked done, and blocking/failing verdicts are routed to
``kanban_block`` / rework instead of fake completion.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

ALLOWED_GATES = frozenset(
    {"spec", "verify", "review", "security", "rules", "qa", "qa-check"}
)
ALLOWED_STATUSES = frozenset({"pass", "warn", "fail"})
ALLOWED_SEVERITIES = frozenset({"info", "warning", "warn", "error"})
REQUIRED_FIELDS = frozenset({
    "schema_version",
    "gate",
    "status",
    "blocking",
    "blockers",
    "affected_files",
    "suggested_next",
})


class GateResultError(ValueError):
    """Raised when a gate-result verdict is malformed or internally unsafe."""


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _validate_blocker(blocker: Any, index: int) -> dict[str, Any]:
    if not isinstance(blocker, Mapping):
        raise GateResultError(f"blockers[{index}] must be an object")

    missing = {"id", "severity", "summary"} - set(blocker)
    if missing:
        raise GateResultError(
            f"blockers[{index}] missing required field(s): {', '.join(sorted(missing))}"
        )

    normalized = dict(blocker)
    for key in ("id", "severity", "summary"):
        if not isinstance(normalized.get(key), str) or not normalized[key].strip():
            raise GateResultError(f"blockers[{index}].{key} must be a non-empty string")
        normalized[key] = normalized[key].strip()

    severity = normalized["severity"]
    if severity not in ALLOWED_SEVERITIES:
        allowed = ", ".join(sorted(ALLOWED_SEVERITIES))
        raise GateResultError(f"blockers[{index}].severity must be one of: {allowed}")

    if "file" in normalized and normalized["file"] is not None:
        if not isinstance(normalized["file"], str):
            raise GateResultError(f"blockers[{index}].file must be a string when present")
        normalized["file"] = normalized["file"].strip()

    return normalized


def validate_gate_result(value: Any) -> dict[str, Any]:
    """Return a normalized gate-result dict or raise :class:`GateResultError`.

    Contract v1 is intentionally compact:
    ``schema_version``, ``gate``, ``status``, ``blocking``, ``blockers``,
    ``affected_files``, and ``suggested_next`` are required.  The accepted gate
    names match the Dev Factory gates and the status vocabulary is pass/warn/fail.
    """

    if not isinstance(value, Mapping):
        raise GateResultError("gate_result must be an object")

    result = dict(value)
    missing = REQUIRED_FIELDS - set(result)
    if missing:
        raise GateResultError(
            f"gate_result missing required field(s): {', '.join(sorted(missing))}"
        )

    if result.get("schema_version") != 1:
        raise GateResultError("gate_result.schema_version must be 1")

    gate = result.get("gate")
    if gate not in ALLOWED_GATES:
        allowed = ", ".join(sorted(ALLOWED_GATES))
        raise GateResultError(f"gate_result.gate must be one of: {allowed}")

    status = result.get("status")
    if status not in ALLOWED_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_STATUSES))
        raise GateResultError(f"gate_result.status must be one of: {allowed}")

    if not isinstance(result.get("blocking"), bool):
        raise GateResultError("gate_result.blocking must be a boolean")

    blockers = result.get("blockers")
    if not isinstance(blockers, list):
        raise GateResultError("gate_result.blockers must be a list")
    result["blockers"] = [_validate_blocker(item, i) for i, item in enumerate(blockers)]

    if not _is_string_list(result.get("affected_files")):
        raise GateResultError("gate_result.affected_files must be a list of strings")

    suggested_next = result.get("suggested_next")
    if not isinstance(suggested_next, Mapping):
        raise GateResultError("gate_result.suggested_next must be an object")
    suggested_next = dict(suggested_next)
    if "action" not in suggested_next or "reason" not in suggested_next:
        raise GateResultError("gate_result.suggested_next requires action and reason")
    action = suggested_next.get("action")
    if action is not None and not isinstance(action, str):
        raise GateResultError("gate_result.suggested_next.action must be a string or null")
    reason = suggested_next.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise GateResultError("gate_result.suggested_next.reason must be a non-empty string")
    suggested_next["reason"] = reason.strip()
    result["suggested_next"] = suggested_next

    if status == "pass" and (result["blocking"] or result["blockers"]):
        raise GateResultError("gate_result.status=pass requires blocking=false and no blockers")
    if status == "fail" and not result["blocking"]:
        raise GateResultError("gate_result.status=fail requires blocking=true")
    if not result["blocking"] and any(
        blocker.get("severity") == "error" for blocker in result["blockers"]
    ):
        raise GateResultError(
            "gate_result with severity=error blockers must set blocking=true"
        )

    return result


def gate_result_blocks_completion(gate_result: Mapping[str, Any]) -> bool:
    """Return True when this verdict must not be completed as done."""

    return bool(gate_result.get("blocking")) or gate_result.get("status") == "fail"
