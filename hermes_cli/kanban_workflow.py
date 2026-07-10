"""Multi-template workflow state machines + convergence-aware review gate.

Port of lee-to's aif-handoff orchestration policies (``stateMachine.ts``,
``reviewGate.ts``, ``autoReviewHandler.ts``) into Hermes kanban terms, plus
Marketing Factory handoff templates (``marketing_fast`` / ``marketing_direct`` /
``marketing_onboarding``) that reuse the same stage/assignee rewrite pattern.

This module is **pure logic** — no sqlite, no I/O — so every branch is
unit-testable. ``kanban_db`` applies the returned patches.

Mapping
-------
One card walks role stages via ``workflow_template_id`` + ``current_step_key``.
Each advance rewrites ``assignee`` to the stage role profile so the existing
dispatcher routes stages without knowing about workflows.

* work stages → ``ready``/``running`` + step key + assignee
* human gates → ``blocked`` / ``needs_input`` + step key (skipped in auto_mode)
* ``verified`` → terminal Hermes ``done``

Convergence on review/verify FAIL returns the card to the workflow's
**rework** stage (AIF: ``implementing``; marketing: ``copy`` / ``produce`` /
``distill``) until max iterations or manual handoff.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

AIF_WORKFLOW_ID = "aif"
MKT_FAST_ID = "marketing_fast"
MKT_DIRECT_ID = "marketing_direct"
MKT_ONBOARDING_ID = "marketing_onboarding"

# AIF stage keys (lee-to vocabulary).
STAGE_SPEC = "spec"
STAGE_PLANNING = "planning"
STAGE_IMPROVE = "improve"
STAGE_PLAN_READY = "plan_ready"
STAGE_IMPLEMENTING = "implementing"
STAGE_VERIFY = "verify"
STAGE_REVIEW = "review"
STAGE_DONE = "done"
STAGE_VERIFIED = "verified"

# Marketing stage keys (handoff factory).
MKT_PLAN = "plan"
MKT_PRODUCE = "produce"
MKT_COPY = "copy"
MKT_VERIFY = "verify"
MKT_REVIEW = "review"
MKT_ACCEPT = "accept"
MKT_OWNER_GATE = "owner_gate"
MKT_SCAFFOLD = "scaffold"
MKT_INTAKE = "intake"
MKT_DISTILL = "distill"
MKT_MEMORY_REVIEW = "memory_review"

WORK_STAGES = (
    STAGE_SPEC, STAGE_PLANNING, STAGE_IMPROVE,
    STAGE_IMPLEMENTING, STAGE_VERIFY, STAGE_REVIEW,
)
HUMAN_GATE_STAGES = (STAGE_PLAN_READY, STAGE_DONE)
ALL_STAGES = WORK_STAGES + HUMAN_GATE_STAGES + (STAGE_VERIFIED,)

STAGE_ROLES: dict[str, str] = {
    STAGE_SPEC: "aif_specifier",
    STAGE_PLANNING: "aif_planner",
    STAGE_IMPROVE: "aif_planner",
    STAGE_IMPLEMENTING: "aif_implementer",
    STAGE_VERIFY: "aif_verifier",
    STAGE_REVIEW: "aif_reviewer",
}

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

HUMAN_ACTIONS_BY_STAGE: dict[str, tuple[str, ...]] = {
    STAGE_PLAN_READY: ("start_implementation", "request_replanning"),
    STAGE_DONE: ("approve_done", "request_changes"),
    MKT_OWNER_GATE: ("approve_done", "request_changes"),
}


# ---------------------------------------------------------------------------
# Workflow registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkflowSpec:
    """One handoff pipeline template (AIF or Marketing)."""
    id: str
    default_entry: str
    roles: Mapping[str, str]                 # stage → profile
    skills: Mapping[str, tuple[str, ...]]    # stage → force-loaded skills
    chain: tuple[str, ...]                   # ordered work stages (no human/terminal)
    rework_stage: str                        # where review FAIL returns
    review_stages: tuple[str, ...]           # stages that use gate_result convergence
    human_gates: tuple[str, ...]             # optional pause stages
    clean_reset_stages: tuple[str, ...] = () # stages that clear convergence flags on entry


_AIF = WorkflowSpec(
    id=AIF_WORKFLOW_ID,
    default_entry=STAGE_PLANNING,
    roles=STAGE_ROLES,
    skills={
        STAGE_SPEC: ("aif-specify", "aif-methodology"),
        STAGE_PLANNING: ("aif-plan", "aif-methodology"),
        STAGE_IMPROVE: ("aif-improve", "aif-methodology"),
        STAGE_IMPLEMENTING: ("aif-implement", "aif-methodology"),
        STAGE_VERIFY: ("aif-verify", "aif-methodology"),
        STAGE_REVIEW: ("aif-review", "aif-security-checklist", "aif-methodology"),
    },
    chain=(STAGE_SPEC, STAGE_PLANNING, STAGE_IMPROVE, STAGE_IMPLEMENTING,
           STAGE_VERIFY, STAGE_REVIEW),
    rework_stage=STAGE_IMPLEMENTING,
    review_stages=(STAGE_VERIFY, STAGE_REVIEW),
    human_gates=(STAGE_PLAN_READY, STAGE_DONE),
    clean_reset_stages=(STAGE_IMPLEMENTING,),
)

_MKT_FAST = WorkflowSpec(
    id=MKT_FAST_ID,
    default_entry=MKT_PRODUCE,
    roles={
        MKT_PRODUCE: "marketing_executor",  # overridden by skill routing when set
        MKT_VERIFY: "marketing_executor",
        MKT_REVIEW: "marketing_reviewer",
        MKT_ACCEPT: "client_marketing",
    },
    skills={
        MKT_PRODUCE: ("mkt-produce", "mkt-verify", "marketing-methodology"),
        MKT_VERIFY: ("mkt-verify", "marketing-methodology"),
        MKT_REVIEW: ("mkt-review-gate", "marketing-review", "marketing-methodology"),
        MKT_ACCEPT: ("mkt-accept", "marketing-methodology"),
    },
    chain=(MKT_PRODUCE, MKT_VERIFY, MKT_REVIEW, MKT_ACCEPT),
    rework_stage=MKT_PRODUCE,
    review_stages=(MKT_VERIFY, MKT_REVIEW),
    human_gates=(MKT_OWNER_GATE,),
    clean_reset_stages=(MKT_PRODUCE,),
)

_MKT_DIRECT = WorkflowSpec(
    id=MKT_DIRECT_ID,
    default_entry=MKT_PLAN,
    roles={
        MKT_PLAN: "client_marketing",
        MKT_COPY: "marketing_copywriter",
        MKT_VERIFY: "marketing_copywriter",
        MKT_REVIEW: "marketing_reviewer",
        MKT_ACCEPT: "client_marketing",
    },
    skills={
        MKT_PLAN: ("mkt-campaign-plan", "mkt-workflows", "marketing-methodology"),
        MKT_COPY: ("mkt-produce", "mkt-verify", "direct-ads-copy", "marketing-methodology"),
        MKT_VERIFY: ("mkt-verify", "marketing-evals", "marketing-methodology"),
        MKT_REVIEW: ("mkt-review-gate", "marketing-review", "marketing-methodology"),
        MKT_ACCEPT: ("mkt-accept", "marketing-methodology"),
    },
    chain=(MKT_PLAN, MKT_COPY, MKT_VERIFY, MKT_REVIEW, MKT_ACCEPT),
    rework_stage=MKT_COPY,
    review_stages=(MKT_VERIFY, MKT_REVIEW),
    human_gates=(MKT_OWNER_GATE,),
    clean_reset_stages=(MKT_COPY,),
)

_MKT_ONBOARDING = WorkflowSpec(
    id=MKT_ONBOARDING_ID,
    default_entry=MKT_SCAFFOLD,
    roles={
        MKT_SCAFFOLD: "client_marketing",
        MKT_INTAKE: "intake_interviewer",
        MKT_DISTILL: "client_marketing",
        MKT_MEMORY_REVIEW: "marketing_reviewer",
        MKT_ACCEPT: "client_marketing",
    },
    skills={
        MKT_SCAFFOLD: ("mkt-brief", "client-knowledge-pack", "marketing-methodology"),
        MKT_INTAKE: ("mkt-produce", "discovery-interview-pro", "client-knowledge-pack"),
        MKT_DISTILL: (
            "client-onboarding-pipeline", "client-knowledge-pack", "marketing-methodology",
        ),
        MKT_MEMORY_REVIEW: ("mkt-review-gate", "marketing-review", "client-knowledge-pack"),
        MKT_ACCEPT: ("mkt-accept", "marketing-methodology"),
    },
    chain=(MKT_SCAFFOLD, MKT_INTAKE, MKT_DISTILL, MKT_MEMORY_REVIEW, MKT_ACCEPT),
    rework_stage=MKT_DISTILL,
    review_stages=(MKT_MEMORY_REVIEW,),
    human_gates=(),
    clean_reset_stages=(MKT_DISTILL,),
)

WORKFLOWS: dict[str, WorkflowSpec] = {
    AIF_WORKFLOW_ID: _AIF,
    MKT_FAST_ID: _MKT_FAST,
    MKT_DIRECT_ID: _MKT_DIRECT,
    MKT_ONBOARDING_ID: _MKT_ONBOARDING,
}

KNOWN_WORKFLOW_IDS: tuple[str, ...] = tuple(WORKFLOWS.keys())


def workflow_id_of(row: Mapping[str, Any]) -> str:
    return (row.get("workflow_template_id") or "").strip()


def get_workflow(workflow_id: Optional[str]) -> Optional[WorkflowSpec]:
    if not workflow_id:
        return None
    return WORKFLOWS.get(workflow_id.strip())


def is_workflow_task(row: Mapping[str, Any]) -> bool:
    """True when this tasks row participates in any registered stage machine."""
    return workflow_id_of(row) in WORKFLOWS


def normalize_entry_stage(
    step_key: Optional[str],
    workflow_id: Optional[str] = None,
) -> str:
    """Resolve entry/current stage for a workflow (default: template default)."""
    step = (step_key or "").strip()
    wf = get_workflow(workflow_id) if workflow_id else None
    if wf is not None:
        known = set(wf.roles) | set(wf.human_gates) | {STAGE_VERIFIED, STAGE_DONE}
        if step in known or step in wf.chain:
            return step
        return wf.default_entry
    # Infer from any template (complete_task often omits explicit id on step check)
    for spec in WORKFLOWS.values():
        known = set(spec.roles) | set(spec.human_gates) | {STAGE_VERIFIED, STAGE_DONE}
        if step in known or step in spec.chain:
            return step
    if step in ALL_STAGES:
        return step
    return STAGE_PLANNING


def stage_role(
    step_key: Optional[str],
    workflow_id: Optional[str] = None,
    row: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Profile that owns a stage. Marketing produce may use pre-set assignee."""
    step = (step_key or "").strip()
    wf = get_workflow(workflow_id) if workflow_id else None
    if wf is None and row is not None:
        wf = get_workflow(workflow_id_of(row))
    if wf is None:
        # Infer from stage name (unique marketing stages; AIF-shared last).
        for spec in WORKFLOWS.values():
            if step in spec.roles:
                wf = spec
                break
    if wf is not None:
        role = wf.roles.get(step)
        # marketing_fast produce: honour explicit assignee if already a known
        # marketing producer (skill-routed at create time).
        if (
            wf.id == MKT_FAST_ID
            and step == MKT_PRODUCE
            and row is not None
        ):
            existing = (row.get("assignee") or "").strip()
            producers = {
                "marketing_executor", "marketing_copywriter", "marketing_designer",
                "marketing_analyst", "smm_manager", "intake_interviewer",
            }
            if existing in producers:
                return existing
        return role
    return STAGE_ROLES.get(step)


def stage_skills(
    step_key: Optional[str],
    workflow_id: Optional[str] = None,
) -> tuple[str, ...]:
    wf = get_workflow(workflow_id)
    if wf is None:
        return ()
    return wf.skills.get((step_key or "").strip(), ())


def is_dispatchable_stage(
    step_key: Optional[str],
    workflow_id: Optional[str] = None,
) -> bool:
    """Gate/terminal stages have no worker; dispatcher must skip them."""
    return stage_role(step_key, workflow_id) is not None


def is_review_gate_stage(
    step_key: Optional[str],
    workflow_id: Optional[str] = None,
) -> bool:
    """Stages whose FAIL goes through convergence (verify/review/memory_review)."""
    step = (step_key or "").strip()
    wf = get_workflow(workflow_id)
    if wf is not None:
        return step in wf.review_stages
    return step in (STAGE_VERIFY, STAGE_REVIEW)


def rework_target(row: Mapping[str, Any]) -> tuple[str, Optional[str]]:
    """(step, assignee) for review-FAIL rework."""
    wf = get_workflow(workflow_id_of(row))
    if wf is None:
        return STAGE_IMPLEMENTING, STAGE_ROLES[STAGE_IMPLEMENTING]
    step = wf.rework_stage
    return step, stage_role(step, wf.id, row)


def resolve_marketing_producer_from_skills(
    skills: Optional[Sequence[str]],
) -> Optional[str]:
    """Map skill name(s) → marketing profile via routing.yaml (if present)."""
    if not skills:
        return None
    try:
        from pathlib import Path
        import yaml  # type: ignore
        path = Path.home() / ".hermes" / "routing" / "marketing-routing.yaml"
        if not path.is_file():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        by_skill = data.get("by_skill") or {}
        for sk in skills:
            key = str(sk).strip()
            if key in by_skill:
                return str(by_skill[key]).strip() or None
            # prefix match
            for sk_name, prof in by_skill.items():
                if key.startswith(str(sk_name)):
                    return str(prof).strip() or None
    except Exception:
        return None
    return None


@dataclass
class StagePatch:
    """One state-machine step, expressed as column updates + bookkeeping."""
    status: str
    step: str
    assignee: Optional[str] = None
    terminal: bool = False
    block_reason: Optional[str] = None
    columns: dict[str, Any] = field(default_factory=dict)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    comment: Optional[str] = None
    skills: Optional[Sequence[str]] = None  # force-load list for next stage


def _flag(row: Mapping[str, Any], key: str, default: bool = False) -> bool:
    val = row.get(key)
    if val is None:
        return default
    return bool(val)


def _work_patch(
    *,
    wf: WorkflowSpec,
    from_step: str,
    next_step: str,
    row: Mapping[str, Any],
    extra_events: Optional[list] = None,
) -> StagePatch:
    cols: dict[str, Any] = {}
    if next_step in wf.clean_reset_stages:
        cols = dict(CLEAN_STATE_RESET)
    skills = stage_skills(next_step, wf.id)
    return StagePatch(
        status="ready",
        step=next_step,
        assignee=stage_role(next_step, wf.id, row),
        columns=cols,
        events=[("workflow_advanced",
                 {"from": from_step, "to": next_step, "workflow": wf.id})]
        + (extra_events or []),
        skills=list(skills) if skills else None,
    )


def _human_gate_patch(
    *,
    wf: WorkflowSpec,
    from_step: str,
    gate_step: str,
) -> StagePatch:
    actions = HUMAN_ACTIONS_BY_STAGE.get(gate_step, ("approve_done", "request_changes"))
    return StagePatch(
        status="blocked",
        step=gate_step,
        assignee=None,
        block_reason=f"workflow human gate '{gate_step}' — actions: {', '.join(actions)}",
        events=[(
            "workflow_human_gate",
            {"from": from_step, "gate": gate_step, "workflow": wf.id,
             "actions": list(actions)},
        )],
    )


def _terminal_verified(from_step: str, workflow: str, auto_mode: bool = False) -> StagePatch:
    return StagePatch(
        status="done",
        step=STAGE_VERIFIED,
        terminal=True,
        columns=dict(CLEAN_STATE_RESET),
        events=[("workflow_advanced",
                 {"from": from_step, "to": STAGE_VERIFIED,
                  "workflow": workflow, "auto_mode": auto_mode})],
    )


def next_stage_on_success(
    row: Mapping[str, Any],
    *,
    run_plan_improve_default: bool = False,
    run_post_verify_default: bool = True,
) -> StagePatch:
    """Advance a workflow card after its current stage completed cleanly."""
    wf_id = workflow_id_of(row) or AIF_WORKFLOW_ID
    wf = get_workflow(wf_id)
    if wf is None:
        wf = _AIF
        wf_id = AIF_WORKFLOW_ID

    step = normalize_entry_stage(row.get("current_step_key"), wf_id)
    auto_mode = _flag(row, "auto_mode", default=True)

    if wf_id == AIF_WORKFLOW_ID:
        return _next_aif(
            row, step=step, auto_mode=auto_mode,
            run_plan_improve_default=run_plan_improve_default,
            run_post_verify_default=run_post_verify_default,
        )

    # Linear marketing chains (fast / direct / onboarding)
    chain = list(wf.chain)
    if step in chain:
        idx = chain.index(step)
        if idx + 1 < len(chain):
            return _work_patch(wf=wf, from_step=step, next_step=chain[idx + 1], row=row)
        # last work stage done → owner_gate (if any and not auto) else verified
        if wf.human_gates and not auto_mode:
            return _human_gate_patch(wf=wf, from_step=step, gate_step=wf.human_gates[0])
        return _terminal_verified(step, wf_id, auto_mode=True)

    if step in wf.human_gates:
        return _terminal_verified(step, wf_id)

    return _terminal_verified(step, wf_id)


def _next_aif(
    row: Mapping[str, Any],
    *,
    step: str,
    auto_mode: bool,
    run_plan_improve_default: bool,
    run_post_verify_default: bool,
) -> StagePatch:
    run_improve = _flag(row, "run_plan_improve", default=run_plan_improve_default)
    run_verify = _flag(row, "run_post_verify", default=run_post_verify_default)
    wf = _AIF

    def _work(next_step: str, extra_events: Optional[list] = None) -> StagePatch:
        return _work_patch(
            wf=wf, from_step=step, next_step=next_step, row=row,
            extra_events=extra_events,
        )

    def _human_gate(gate_step: str) -> StagePatch:
        return _human_gate_patch(wf=wf, from_step=step, gate_step=gate_step)

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
            return _terminal_verified(step, AIF_WORKFLOW_ID, auto_mode=True)
        return _human_gate(STAGE_DONE)
    return _terminal_verified(step, AIF_WORKFLOW_ID)


def apply_human_event(row: Mapping[str, Any], event: str) -> StagePatch:
    """Human actions on gate stages (AIF plan_ready/done + marketing owner_gate)."""
    step = (row.get("current_step_key") or "").strip()
    wf_id = workflow_id_of(row) or AIF_WORKFLOW_ID
    wf = get_workflow(wf_id) or _AIF

    if event == "start_implementation":
        if step != STAGE_PLAN_READY:
            raise ValueError("start_implementation is only allowed from plan_ready")
        return _work_patch(
            wf=_AIF, from_step=step, next_step=STAGE_IMPLEMENTING, row=row,
            extra_events=[("workflow_human_action",
                           {"action": event, "from": step, "to": STAGE_IMPLEMENTING})],
        )
    if event == "request_replanning":
        if step != STAGE_PLAN_READY:
            raise ValueError("request_replanning is only allowed from plan_ready")
        return _work_patch(
            wf=_AIF, from_step=step, next_step=STAGE_PLANNING, row=row,
            extra_events=[("workflow_human_action",
                           {"action": event, "from": step, "to": STAGE_PLANNING})],
        )
    if event == "approve_done":
        if step not in (STAGE_DONE, MKT_OWNER_GATE):
            raise ValueError("approve_done is only allowed from done or owner_gate")
        return StagePatch(
            status="done", step=STAGE_VERIFIED, terminal=True,
            columns=dict(CLEAN_STATE_RESET),
            events=[("workflow_human_action",
                     {"action": event, "from": step, "to": STAGE_VERIFIED,
                      "workflow": wf_id})],
        )
    if event == "request_changes":
        if step not in (STAGE_DONE, MKT_OWNER_GATE):
            raise ValueError("request_changes is only allowed from done or owner_gate")
        rework_step, rework_assignee = rework_target(row)
        cols = dict(CLEAN_STATE_RESET)
        cols["rework_requested"] = 1
        return StagePatch(
            status="ready", step=rework_step,
            assignee=rework_assignee,
            columns=cols,
            skills=list(stage_skills(rework_step, wf_id)) or None,
            events=[("workflow_human_action",
                     {"action": event, "from": step, "to": rework_step,
                      "workflow": wf_id})],
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
