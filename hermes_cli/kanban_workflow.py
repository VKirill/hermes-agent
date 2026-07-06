"""AIF workflow state machine + convergence-aware review gate.

Port of lee-to's aif-handoff orchestration policies (``stateMachine.ts``,
``reviewGate.ts``, ``autoReviewHandler.ts``) into Hermes kanban terms. This
module is **pure logic** — no sqlite, no I/O — so every branch of the
decision tree is unit-testable. ``kanban_db`` applies the returned patches.

Mapping between the two worlds
------------------------------

lee-to models ONE task card walking through role stages; Hermes dispatches
one worker per (task, assignee). The bridge: a task with
``workflow_template_id='aif'`` carries its stage in ``current_step_key``,
and every stage transition rewrites ``assignee`` to the stage's role
profile — so the existing dispatcher routes stages with zero changes.

Status mapping (lee-to → Hermes ``(status, current_step_key)``):

* auto work stages (planning/improve/implementing/verify/review)
  → ``ready``/``running`` + that step key
* human gates (plan_ready, done-approval) → ``blocked`` with
  ``block_kind='needs_input'`` + that step key (auto_mode skips them)
* ``verified`` (terminal) → Hermes ``status='done'`` + step ``verified``.
  A workflow card is **never** ``status='done'`` before verification, so
  parent-gating of child tasks keeps its meaning.

The convergence gate ("never guess convergence from malformed output",
iteration cap → human) fires on review/verify FAIL verdicts: instead of
parking the card in ``blocked`` forever or spawning unbounded rework, the
card is sent back to ``implementing`` with the findings carried in
``auto_review_state`` — until the cap trips or new blockers appear after
old ones were closed, at which point a human gets it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

AIF_WORKFLOW_ID = "aif"

# Stage keys reuse lee-to's vocabulary so their docs/skills read 1:1.
STAGE_SPEC = "spec"
STAGE_PLANNING = "planning"
STAGE_IMPROVE = "improve"
STAGE_PLAN_READY = "plan_ready"     # human gate (skipped in auto_mode)
STAGE_IMPLEMENTING = "implementing"
STAGE_VERIFY = "verify"
STAGE_REVIEW = "review"
STAGE_DONE = "done"                 # human approval gate (skipped in auto_mode)
STAGE_VERIFIED = "verified"         # terminal

WORK_STAGES = (
    STAGE_SPEC, STAGE_PLANNING, STAGE_IMPROVE,
    STAGE_IMPLEMENTING, STAGE_VERIFY, STAGE_REVIEW,
)
HUMAN_GATE_STAGES = (STAGE_PLAN_READY, STAGE_DONE)
ALL_STAGES = WORK_STAGES + HUMAN_GATE_STAGES + (STAGE_VERIFIED,)

# Stage → Hermes profile that works it. Gate stages have no worker: the
# dispatcher must never spawn for them (see is_dispatchable_stage).
STAGE_ROLES: dict[str, str] = {
    STAGE_SPEC: "aif_specifier",
    STAGE_PLANNING: "aif_planner",
    STAGE_IMPROVE: "aif_planner",
    STAGE_IMPLEMENTING: "aif_implementer",
    STAGE_VERIFY: "aif_verifier",
    STAGE_REVIEW: "aif_reviewer",
}

# Convergence flags cleared on every clean transition (lee-to
# CLEAN_STATE_RESET). Keys are tasks-table columns; kanban_db turns this
# into an UPDATE. The audit trail lives in task_events/comments, not on
# the live fields that drive future automation decisions.
CLEAN_STATE_RESET: dict[str, Any] = {
    "rework_requested": 0,
    "review_iteration_count": 0,
    "manual_review_required": 0,
    "auto_review_state": None,
}

DEFAULT_MAX_REVIEW_ITERATIONS = 3
STRATEGY_FULL_RE_REVIEW = "full_re_review"
STRATEGY_CLOSURE_FIRST = "closure_first"
VALID_REVIEW_STRATEGIES = (STRATEGY_FULL_RE_REVIEW, STRATEGY_CLOSURE_FIRST)

# Human actions available per stage (port of HUMAN_ACTIONS_BY_STATUS).
# Only gate stages (and blocked cards) offer actions; auto stages have none.
HUMAN_ACTIONS_BY_STAGE: dict[str, tuple[str, ...]] = {
    STAGE_PLAN_READY: ("start_implementation", "request_replanning"),
    STAGE_DONE: ("approve_done", "request_changes"),
}


def is_workflow_task(row: Mapping[str, Any]) -> bool:
    """True when this tasks row participates in the AIF stage machine."""
    return (row.get("workflow_template_id") or "").strip() == AIF_WORKFLOW_ID


def normalize_entry_stage(step_key: Optional[str]) -> str:
    """Stage a new workflow card starts in (default: planning).

    ``spec`` is Hermes's own optional pre-stage (lee-to has no specifier);
    it is honoured only when explicitly requested at creation.
    """
    step = (step_key or "").strip()
    if step in ALL_STAGES:
        return step
    return STAGE_PLANNING


def stage_role(step_key: Optional[str]) -> Optional[str]:
    return STAGE_ROLES.get((step_key or "").strip())


def is_dispatchable_stage(step_key: Optional[str]) -> bool:
    """Gate/terminal stages have no worker; the dispatcher must skip them."""
    return (step_key or "").strip() in STAGE_ROLES


@dataclass
class StagePatch:
    """One state-machine step, expressed as column updates + bookkeeping.

    ``status``/``step``/``assignee`` describe where the card lands.
    ``terminal`` means "complete for real" (Hermes done + step verified).
    ``block_reason`` is set when the card lands in ``blocked`` (human gate
    or manual review handoff). ``events`` are (event_name, payload) pairs
    for the task_events audit trail; ``comment`` (if any) is a
    human-readable summary posted to task_comments.
    """
    status: str
    step: str
    assignee: Optional[str] = None
    terminal: bool = False
    block_reason: Optional[str] = None
    columns: dict[str, Any] = field(default_factory=dict)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    comment: Optional[str] = None


def _flag(row: Mapping[str, Any], key: str, default: bool = False) -> bool:
    val = row.get(key)
    if val is None:
        return default
    return bool(val)


def next_stage_on_success(
    row: Mapping[str, Any],
    *,
    run_plan_improve_default: bool = False,
    run_post_verify_default: bool = True,
) -> StagePatch:
    """Advance a workflow card after its current stage completed cleanly.

    Port of the coordinator's stage table: planning→plan_ready,
    implementing→review (via verify when enabled), review→done — with the
    two human gates collapsed away when ``auto_mode`` is on. Verify/review
    SUCCESS lands here; their FAIL verdicts go through
    :func:`evaluate_review_gate` instead.
    """
    step = normalize_entry_stage(row.get("current_step_key"))
    auto_mode = _flag(row, "auto_mode", default=True)
    run_improve = _flag(row, "run_plan_improve", default=run_plan_improve_default)
    run_verify = _flag(row, "run_post_verify", default=run_post_verify_default)

    def _work(next_step: str, extra_events: Optional[list] = None) -> StagePatch:
        return StagePatch(
            status="ready",
            step=next_step,
            assignee=STAGE_ROLES[next_step],
            columns=dict(CLEAN_STATE_RESET) if next_step == STAGE_IMPLEMENTING else {},
            events=[("workflow_advanced", {"from": step, "to": next_step})]
            + (extra_events or []),
        )

    def _human_gate(gate_step: str) -> StagePatch:
        actions = ", ".join(HUMAN_ACTIONS_BY_STAGE[gate_step])
        return StagePatch(
            status="blocked",
            step=gate_step,
            assignee=None,
            block_reason=f"workflow human gate '{gate_step}' — actions: {actions}",
            events=[(
                "workflow_human_gate",
                {"from": step, "gate": gate_step,
                 "actions": list(HUMAN_ACTIONS_BY_STAGE[gate_step])},
            )],
        )

    if step == STAGE_SPEC:
        return _work(STAGE_PLANNING)
    if step in (STAGE_PLANNING, STAGE_IMPROVE):
        if step == STAGE_PLANNING and run_improve:
            return _work(STAGE_IMPROVE)
        if auto_mode:
            return _work(STAGE_IMPLEMENTING)
        return _human_gate(STAGE_PLAN_READY)
    if step == STAGE_IMPLEMENTING:
        return _work(STAGE_VERIFY if run_verify else STAGE_REVIEW)
    if step == STAGE_VERIFY:
        return _work(STAGE_REVIEW)
    if step == STAGE_REVIEW:
        if auto_mode:
            # done-approval gate skipped: review PASS is the acceptance
            # authority (department law) → straight to terminal verified.
            return StagePatch(
                status="done",
                step=STAGE_VERIFIED,
                terminal=True,
                columns=dict(CLEAN_STATE_RESET),
                events=[("workflow_advanced",
                         {"from": step, "to": STAGE_VERIFIED, "auto_mode": True})],
            )
        return _human_gate(STAGE_DONE)
    # Completing a card already at a gate/terminal step (CLI misuse):
    # treat as approval of the whole card.
    return StagePatch(
        status="done",
        step=STAGE_VERIFIED,
        terminal=True,
        columns=dict(CLEAN_STATE_RESET),
        events=[("workflow_advanced", {"from": step, "to": STAGE_VERIFIED})],
    )


def apply_human_event(row: Mapping[str, Any], event: str) -> StagePatch:
    """Port of ``applyHumanTaskEvent`` — human actions on gate stages.

    Raises ``ValueError`` with the same guard semantics lee-to uses
    ("X is only allowed from Y") when the action doesn't fit the stage.
    """
    step = (row.get("current_step_key") or "").strip()

    if event == "start_implementation":
        if step != STAGE_PLAN_READY:
            raise ValueError("start_implementation is only allowed from plan_ready")
        return StagePatch(
            status="ready", step=STAGE_IMPLEMENTING,
            assignee=STAGE_ROLES[STAGE_IMPLEMENTING],
            columns=dict(CLEAN_STATE_RESET),
            events=[("workflow_human_action",
                     {"action": event, "from": step, "to": STAGE_IMPLEMENTING})],
        )
    if event == "request_replanning":
        if step != STAGE_PLAN_READY:
            raise ValueError("request_replanning is only allowed from plan_ready")
        return StagePatch(
            status="ready", step=STAGE_PLANNING,
            assignee=STAGE_ROLES[STAGE_PLANNING],
            columns=dict(CLEAN_STATE_RESET),
            events=[("workflow_human_action",
                     {"action": event, "from": step, "to": STAGE_PLANNING})],
        )
    if event == "approve_done":
        if step != STAGE_DONE:
            raise ValueError("approve_done is only allowed from done")
        return StagePatch(
            status="done", step=STAGE_VERIFIED, terminal=True,
            columns=dict(CLEAN_STATE_RESET),
            events=[("workflow_human_action",
                     {"action": event, "from": step, "to": STAGE_VERIFIED})],
        )
    if event == "request_changes":
        if step != STAGE_DONE:
            raise ValueError("request_changes is only allowed from done")
        cols = dict(CLEAN_STATE_RESET)
        cols["rework_requested"] = 1  # reset-then-set, exactly like lee-to
        return StagePatch(
            status="ready", step=STAGE_IMPLEMENTING,
            assignee=STAGE_ROLES[STAGE_IMPLEMENTING],
            columns=cols,
            events=[("workflow_human_action",
                     {"action": event, "from": step, "to": STAGE_IMPLEMENTING})],
        )
    raise ValueError(f"unknown workflow human event: {event}")


# ---------------------------------------------------------------------------
# Convergence-aware review gate (reviewGate.ts + autoReviewHandler.ts)
# ---------------------------------------------------------------------------

def finding_id(source: str, text: str) -> str:
    """Stable finding id — same (source, normalized text) → same id.

    Mirrors lee-to's createAutoReviewFindingId: convergence can only be
    proven when the same complaint hashes to the same id across rounds.
    """
    normalized = " ".join((text or "").split()).lower()
    digest = hashlib.sha256(f"{source}|{normalized}".encode("utf-8")).hexdigest()
    return f"f_{digest[:12]}"


def findings_from_gate_result(gate_result: Optional[Mapping[str, Any]]) -> list[dict]:
    """Extract convergence findings from a validated gate_result.

    ``blockers`` in the department contract already carry stable string
    ids; when a blocker id looks author-invented (non-deterministic across
    rounds), we key on the content hash instead so re-review comparisons
    don't depend on the reviewer re-typing the same id.
    """
    if not gate_result:
        return []
    findings: list[dict] = []
    gate = str(gate_result.get("gate") or "review")
    for blocker in gate_result.get("blockers") or []:
        summary = str(blocker.get("summary") or "").strip()
        if not summary:
            continue
        findings.append({
            "id": finding_id(gate, summary),
            "source": gate,
            "declared_id": str(blocker.get("id") or "").strip() or None,
            "severity": str(blocker.get("severity") or "error"),
            "file": blocker.get("file"),
            "text": summary,
        })
    return findings


def parse_auto_review_state(raw: Optional[str]) -> dict[str, Any]:
    """Decode the persisted ``auto_review_state`` JSON column (fail-open)."""
    if not raw:
        return {}
    try:
        state = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def to_auto_review_state(
    *, strategy: str, iteration: int, findings: list[dict]
) -> str:
    return json.dumps(
        {"strategy": strategy, "iteration": iteration, "findings": findings},
        ensure_ascii=False,
    )


@dataclass
class ReviewGateDecision:
    """Outcome of one convergence-gate evaluation.

    ``status`` ∈ success | rework | manual. ``handoff_reason`` set for
    manual (max_iterations | new_blockers_after_rework |
    malformed_review_output). ``metrics`` feeds the Auto Review Gate
    Summary comment and the task_events payload.
    """
    status: str
    iteration: int
    max_iterations: int
    findings: list[dict] = field(default_factory=list)
    handoff_reason: Optional[str] = None
    metrics: dict[str, Any] = field(default_factory=dict)
    auto_review_state: Optional[str] = None


def evaluate_review_gate(
    row: Mapping[str, Any],
    gate_result: Optional[Mapping[str, Any]],
    *,
    strategy: str = STRATEGY_FULL_RE_REVIEW,
    max_iterations_default: int = DEFAULT_MAX_REVIEW_ITERATIONS,
) -> ReviewGateDecision:
    """Decide success / rework / manual for a review-stage FAIL (or PASS).

    Port of ``buildStructuredDecision`` + the max-iterations guard from
    ``handleAutoReviewGate``:

    * no blocking findings → success
    * blockers, iteration < cap → rework (back to implementing, findings
      carried in auto_review_state)
    * blockers, iteration ≥ cap → manual (max_iterations)
    * closure_first: previous findings all resolved but NEW blockers
      appeared → manual (new_blockers_after_rework)
    * ``gate_result is None`` (unstructured block) with previous findings
      → manual (malformed_review_output). Structured output is the only
      path that can prove a previous blocker was actually resolved —
      never guess convergence from malformed output. Without previous
      findings the block reason is synthesized into a single finding and
      treated as round one of rework (lee-to's fallback-extraction
      analog; in Hermes the tool boundary already forces gate workers to
      emit gate_result, so this path is CLI-misuse insurance).
    """
    if strategy not in VALID_REVIEW_STRATEGIES:
        strategy = STRATEGY_FULL_RE_REVIEW

    prev_state = parse_auto_review_state(row.get("auto_review_state"))
    prev_findings = [
        f for f in (prev_state.get("findings") or []) if isinstance(f, dict)
    ]
    prev_ids = {f.get("id") for f in prev_findings if f.get("id")}

    iteration = int(row.get("review_iteration_count") or 0) + 1
    raw_cap = row.get("max_review_iterations")
    max_iterations = int(raw_cap) if raw_cap else int(max_iterations_default)
    if max_iterations < 1:
        max_iterations = 1

    malformed = gate_result is None
    if malformed:
        findings: list[dict] = []
    else:
        findings = findings_from_gate_result(gate_result)

    still_ids = prev_ids & {f["id"] for f in findings}
    new_findings = [f for f in findings if f["id"] not in prev_ids]
    metrics = {
        "strategy": strategy,
        "parser_mode": "fallback" if malformed else "structured",
        "iteration": iteration,
        "max_iterations": max_iterations,
        "previous_blocking_count": len(prev_findings),
        "still_blocking_count": len(still_ids),
        "new_blocking_count": len(new_findings),
        "total_blocking_count": len(findings),
    }

    if malformed:
        if prev_findings:
            # Preserve ALL previous blockers and escalate; do not guess
            # that an unparseable verdict means the loop converged.
            state = to_auto_review_state(
                strategy=strategy, iteration=iteration, findings=prev_findings
            )
            metrics["total_blocking_count"] = len(prev_findings)
            return ReviewGateDecision(
                status="manual", iteration=iteration,
                max_iterations=max_iterations, findings=prev_findings,
                handoff_reason="malformed_review_output",
                metrics=metrics, auto_review_state=state,
            )
        reason = str(row.get("_block_reason") or "review failed").strip()
        synthesized = [{
            "id": finding_id("review", reason),
            "source": "review",
            "declared_id": None,
            "severity": "error",
            "file": None,
            "text": reason[:500],
        }]
        metrics["total_blocking_count"] = 1
        metrics["new_blocking_count"] = 1
        if iteration >= max_iterations:
            state = to_auto_review_state(
                strategy=strategy, iteration=iteration, findings=synthesized
            )
            return ReviewGateDecision(
                status="manual", iteration=iteration,
                max_iterations=max_iterations, findings=synthesized,
                handoff_reason="max_iterations",
                metrics=metrics, auto_review_state=state,
            )
        state = to_auto_review_state(
            strategy=strategy, iteration=iteration, findings=synthesized
        )
        return ReviewGateDecision(
            status="rework", iteration=iteration,
            max_iterations=max_iterations, findings=synthesized,
            metrics=metrics, auto_review_state=state,
        )

    if not findings:
        return ReviewGateDecision(
            status="success", iteration=iteration,
            max_iterations=max_iterations, metrics=metrics,
        )

    state = to_auto_review_state(
        strategy=strategy, iteration=iteration, findings=findings
    )

    if (
        strategy == STRATEGY_CLOSURE_FIRST
        and prev_findings
        and not still_ids
        and new_findings
    ):
        return ReviewGateDecision(
            status="manual", iteration=iteration,
            max_iterations=max_iterations, findings=findings,
            handoff_reason="new_blockers_after_rework",
            metrics=metrics, auto_review_state=state,
        )

    if iteration >= max_iterations:
        return ReviewGateDecision(
            status="manual", iteration=iteration,
            max_iterations=max_iterations, findings=findings,
            handoff_reason="max_iterations",
            metrics=metrics, auto_review_state=state,
        )

    return ReviewGateDecision(
        status="rework", iteration=iteration,
        max_iterations=max_iterations, findings=findings,
        metrics=metrics, auto_review_state=state,
    )


def build_gate_summary(decision: ReviewGateDecision) -> str:
    """Human-readable Auto Review Gate Summary (posted as a task comment)."""
    m = decision.metrics
    outcome = {
        "success": "success",
        "rework": "request_changes",
        "manual": "manual_review_required",
    }.get(decision.status, decision.status)
    lines = [
        "## Auto Review Gate Summary",
        f"- Outcome: {outcome}",
        f"- Strategy: {m.get('strategy')}",
        f"- Parser mode: {m.get('parser_mode')}",
        f"- Review iteration: {decision.iteration}/{decision.max_iterations}",
        f"- Previous blocking findings: {m.get('previous_blocking_count', 0)}",
        f"- Still-blocking previous findings: {m.get('still_blocking_count', 0)}",
        f"- New blocking findings: {m.get('new_blocking_count', 0)}",
        f"- Total blocking findings: {m.get('total_blocking_count', 0)}",
    ]
    if decision.handoff_reason:
        lines.append(f"- Handoff reason: {decision.handoff_reason}")
    lines.append("")
    if decision.status == "success":
        lines.append("Review passed the auto-gate; advancing the card.")
        return "\n".join(lines)
    if decision.status == "manual":
        lines.append(
            "Automatic review convergence stopped. "
            "Human review is required before final resolution."
        )
    else:
        lines.append(
            "Automatic review found blocking issues. "
            "Returning the card to implementing."
        )
    lines.append("")
    lines.append("## Blocking Findings")
    if decision.findings:
        for f in decision.findings:
            lines.append(f"- [{f['id']}] {f['source']} | {f['text']}")
    else:
        lines.append("- none")
    return "\n".join(lines)
