"""AIF workflow stage machine + convergence review gate.

Port of lee-to's aif-handoff orchestration (stateMachine.ts / reviewGate.ts
/ autoReviewHandler.ts) — see ``hermes_cli/kanban_workflow.py``. Covers:

* pure state machine: stage advances, optional improve/verify stages,
  human gates vs auto mode, human gate actions and their guards
* convergence gate decision tree: success / rework / manual on
  max_iterations, new_blockers_after_rework (closure_first), and the
  malformed-output fail-closed path ("never guess convergence from
  malformed output")
* DB integration: one card walks planning → implementing → verify →
  review → verified with the assignee rewritten per stage; review FAIL
  routes rework with findings carried across rounds; the iteration cap
  stops the loop at a human gate; generic unblock refuses human gates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb
from hermes_cli import kanban_workflow as kwf


@pytest.fixture
def kanban_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def _gate(status="pass", blockers=(), gate="review"):
    blocking = status == "fail"
    return {
        "schema_version": 1,
        "gate": gate,
        "status": status,
        "blocking": blocking,
        "blockers": [
            {"id": f"b{i}", "severity": "error", "summary": text}
            for i, text in enumerate(blockers)
        ],
        "affected_files": [],
        "suggested_next": {"action": None, "reason": "test"},
    }


def _row(**overrides):
    base = {
        "workflow_template_id": "aif",
        "current_step_key": "review",
        "auto_mode": None,
        "review_iteration_count": 0,
        "max_review_iterations": None,
        "auto_review_state": None,
        "rework_requested": 0,
        "run_plan_improve": None,
        "run_post_verify": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Pure state machine
# ---------------------------------------------------------------------------


def test_auto_mode_chain_skips_human_gates():
    p = kwf.next_stage_on_success(_row(current_step_key="planning"))
    assert (p.status, p.step, p.assignee) == ("ready", "implementing", "aif_implementer")

    p = kwf.next_stage_on_success(_row(current_step_key="implementing"))
    assert (p.step, p.assignee) == ("verify", "aif_verifier")

    p = kwf.next_stage_on_success(_row(current_step_key="verify"))
    assert (p.step, p.assignee) == ("review", "aif_reviewer")

    p = kwf.next_stage_on_success(_row(current_step_key="review"))
    assert p.terminal and (p.status, p.step) == ("done", "verified")


def test_spec_enters_planning():
    p = kwf.next_stage_on_success(_row(current_step_key="spec"))
    assert (p.step, p.assignee) == ("planning", "aif_planner")


def test_run_plan_improve_inserts_improve_stage():
    p = kwf.next_stage_on_success(_row(current_step_key="planning", run_plan_improve=1))
    assert (p.step, p.assignee) == ("improve", "aif_planner")
    p = kwf.next_stage_on_success(_row(current_step_key="improve"))
    assert p.step == "implementing"


def test_run_post_verify_off_goes_straight_to_review():
    p = kwf.next_stage_on_success(_row(current_step_key="implementing", run_post_verify=0))
    assert p.step == "review"


def test_human_gates_pause_at_plan_ready_and_done():
    p = kwf.next_stage_on_success(_row(current_step_key="planning", auto_mode=0))
    assert (p.status, p.step) == ("blocked", "plan_ready")
    assert not p.terminal

    p = kwf.next_stage_on_success(_row(current_step_key="review", auto_mode=0))
    assert (p.status, p.step) == ("blocked", "done")


def test_advance_into_implementing_applies_clean_state_reset():
    p = kwf.next_stage_on_success(_row(current_step_key="planning"))
    assert p.columns["review_iteration_count"] == 0
    assert p.columns["auto_review_state"] is None
    assert p.columns["rework_requested"] == 0
    assert p.columns["manual_review_required"] == 0


def test_human_events_guards_and_transitions():
    ok = kwf.apply_human_event(_row(current_step_key="done"), "approve_done")
    assert ok.terminal and ok.step == "verified"

    rework = kwf.apply_human_event(_row(current_step_key="done"), "request_changes")
    assert (rework.status, rework.step) == ("ready", "implementing")
    # reset-then-set, exactly like lee-to's CLEAN_STATE_RESET + reworkRequested
    assert rework.columns["rework_requested"] == 1
    assert rework.columns["review_iteration_count"] == 0

    start = kwf.apply_human_event(_row(current_step_key="plan_ready"), "start_implementation")
    assert (start.step, start.assignee) == ("implementing", "aif_implementer")

    replan = kwf.apply_human_event(_row(current_step_key="plan_ready"), "request_replanning")
    assert (replan.step, replan.assignee) == ("planning", "aif_planner")

    with pytest.raises(ValueError, match="only allowed from done"):
        kwf.apply_human_event(_row(current_step_key="review"), "approve_done")
    with pytest.raises(ValueError, match="only allowed from plan_ready"):
        kwf.apply_human_event(_row(current_step_key="done"), "start_implementation")
    with pytest.raises(ValueError, match="unknown workflow human event"):
        kwf.apply_human_event(_row(current_step_key="done"), "yolo")


def test_finding_ids_are_stable_across_formatting():
    a = kwf.finding_id("review", "SQL injection  in login\n")
    b = kwf.finding_id("review", "sql injection in LOGIN")
    assert a == b
    assert a != kwf.finding_id("review", "different problem")
    assert a != kwf.finding_id("security", "SQL injection in login")


# ---------------------------------------------------------------------------
# Convergence gate decision tree
# ---------------------------------------------------------------------------


def test_gate_success_on_no_blockers():
    d = kwf.evaluate_review_gate(_row(), _gate("pass"))
    assert d.status == "success"
    assert d.metrics["parser_mode"] == "structured"


def test_gate_rework_below_cap_carries_findings():
    d = kwf.evaluate_review_gate(_row(), _gate("fail", ["bug A", "bug B"]))
    assert d.status == "rework"
    assert d.iteration == 1
    state = json.loads(d.auto_review_state)
    assert {f["text"] for f in state["findings"]} == {"bug A", "bug B"}


def test_gate_manual_at_max_iterations():
    prev = kwf.to_auto_review_state(
        strategy="full_re_review", iteration=2,
        findings=kwf.findings_from_gate_result(_gate("fail", ["bug A"])),
    )
    d = kwf.evaluate_review_gate(
        _row(review_iteration_count=2, auto_review_state=prev),
        _gate("fail", ["bug A"]),
        max_iterations_default=3,
    )
    assert d.status == "manual"
    assert d.handoff_reason == "max_iterations"
    assert d.iteration == 3


def test_gate_per_task_cap_overrides_default():
    d = kwf.evaluate_review_gate(
        _row(max_review_iterations=1), _gate("fail", ["bug A"]),
        max_iterations_default=5,
    )
    assert d.status == "manual"
    assert d.handoff_reason == "max_iterations"


def test_closure_first_escalates_on_new_blockers_after_rework():
    prev = kwf.to_auto_review_state(
        strategy="closure_first", iteration=1,
        findings=kwf.findings_from_gate_result(_gate("fail", ["bug A"])),
    )
    d = kwf.evaluate_review_gate(
        _row(review_iteration_count=1, auto_review_state=prev),
        _gate("fail", ["totally new bug"]),
        strategy="closure_first",
    )
    assert d.status == "manual"
    assert d.handoff_reason == "new_blockers_after_rework"
    assert d.metrics["still_blocking_count"] == 0
    assert d.metrics["new_blocking_count"] == 1


def test_full_re_review_keeps_reworking_on_new_blockers():
    prev = kwf.to_auto_review_state(
        strategy="full_re_review", iteration=1,
        findings=kwf.findings_from_gate_result(_gate("fail", ["bug A"])),
    )
    d = kwf.evaluate_review_gate(
        _row(review_iteration_count=1, auto_review_state=prev),
        _gate("fail", ["totally new bug"]),
        strategy="full_re_review",
    )
    assert d.status == "rework"


def test_malformed_with_previous_findings_escalates_and_preserves_them():
    # Structured output is the only path that can prove a previous blocker
    # was resolved — malformed output must never read as convergence.
    prev = kwf.to_auto_review_state(
        strategy="full_re_review", iteration=1,
        findings=kwf.findings_from_gate_result(_gate("fail", ["bug A"])),
    )
    d = kwf.evaluate_review_gate(
        _row(review_iteration_count=1, auto_review_state=prev), None,
    )
    assert d.status == "manual"
    assert d.handoff_reason == "malformed_review_output"
    assert [f["text"] for f in d.findings] == ["bug A"]
    assert d.metrics["parser_mode"] == "fallback"


def test_malformed_first_round_synthesizes_finding_and_reworks():
    d = kwf.evaluate_review_gate(
        _row(_block_reason="tests are red"), None,
    )
    assert d.status == "rework"
    assert d.findings[0]["text"] == "tests are red"


# ---------------------------------------------------------------------------
# DB integration — one card walks the whole pipeline
# ---------------------------------------------------------------------------


def _step(conn, tid):
    r = conn.execute(
        "SELECT status, assignee, current_step_key, rework_requested, "
        "review_iteration_count, manual_review_required, block_kind, "
        "auto_review_state FROM tasks WHERE id=?",
        (tid,),
    ).fetchone()
    return dict(r)


def test_workflow_create_forces_stage_role(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        tid = kb.create_task(
            conn, title="build feature", assignee="someone_else", workflow="aif",
        )
        row = _step(conn, tid)
        assert row["assignee"] == "aif_planner"
        assert row["current_step_key"] == "planning"


def test_workflow_step_requires_workflow(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        with pytest.raises(ValueError, match="workflow_step requires"):
            kb.create_task(conn, title="x", workflow_step="review")


def test_full_auto_pipeline_advances_and_terminates(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="ship it", workflow="aif")

        assert kb.complete_task(conn, tid, result="plan done")
        row = _step(conn, tid)
        assert (row["status"], row["current_step_key"], row["assignee"]) == (
            "ready", "implementing", "aif_implementer",
        )

        assert kb.complete_task(conn, tid, result="code done")
        assert _step(conn, tid)["current_step_key"] == "verify"

        assert kb.complete_task(
            conn, tid, result="verify pass",
            metadata={"gate_result": _gate("pass", gate="verify")},
        )
        assert _step(conn, tid)["current_step_key"] == "review"

        assert kb.complete_task(
            conn, tid, result="review pass",
            metadata={"gate_result": _gate("pass")},
        )
        row = _step(conn, tid)
        assert (row["status"], row["current_step_key"]) == ("done", "verified")


def test_review_fail_routes_rework_with_findings(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="ship it", workflow="aif", workflow_step="review")
        ok = kb.block_task(
            conn, tid, reason="review failed", kind="needs_input",
            gate_result=_gate("fail", ["missing error handling"]),
        )
        assert ok
        row = _step(conn, tid)
        assert (row["status"], row["current_step_key"], row["assignee"]) == (
            "ready", "implementing", "aif_implementer",
        )
        assert row["rework_requested"] == 1
        assert row["review_iteration_count"] == 1
        state = json.loads(row["auto_review_state"])
        assert state["findings"][0]["text"] == "missing error handling"
        # rework findings surface in the next worker's context
        ctx = kb.build_worker_context(conn, tid)
        assert "REWORK ROUND" in ctx
        assert "missing error handling" in ctx


def test_iteration_cap_stops_loop_at_human_gate(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="ship it", workflow="aif", workflow_step="review")
        with kb.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET max_review_iterations=2 WHERE id=?", (tid,)
            )
        # round 1: rework
        assert kb.block_task(
            conn, tid, reason="fail 1",
            gate_result=_gate("fail", ["bug A"]),
        )
        assert _step(conn, tid)["current_step_key"] == "implementing"
        # implementer finishes rework; verify off to land straight in review
        with kb.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET run_post_verify=0 WHERE id=?", (tid,)
            )
        assert kb.complete_task(conn, tid, result="rework done")
        assert _step(conn, tid)["current_step_key"] == "review"
        # round 2: still failing → cap reached → manual handoff, NOT rework
        assert kb.block_task(
            conn, tid, reason="fail 2",
            gate_result=_gate("fail", ["bug A"]),
        )
        row = _step(conn, tid)
        assert (row["status"], row["current_step_key"]) == ("blocked", "done")
        assert row["manual_review_required"] == 1
        assert row["block_kind"] == "needs_input"
        assert row["review_iteration_count"] == 2

        # generic unblock refuses the human gate…
        assert not kb.unblock_task(conn, tid)
        # …but the explicit human actions resolve it
        assert kb.apply_workflow_human_event(conn, tid, "request_changes")
        row = _step(conn, tid)
        assert (row["status"], row["current_step_key"]) == ("ready", "implementing")
        assert row["rework_requested"] == 1
        assert row["review_iteration_count"] == 0  # human rework resets convergence


def test_approve_done_completes_terminally(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="ship it", workflow="aif", workflow_step="review")
        assert kb.block_task(
            conn, tid, reason="unstructured fail",
            gate_result=None,
        )
        # first malformed round synthesizes a finding and reworks
        assert _step(conn, tid)["current_step_key"] == "implementing"
        with kb.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET run_post_verify=0, max_review_iterations=1 "
                "WHERE id=?", (tid,),
            )
        assert kb.complete_task(conn, tid, result="rework done")
        # cap=1 → next fail goes manual
        assert kb.block_task(
            conn, tid, reason="still bad",
            gate_result=_gate("fail", ["bug B"]),
        )
        assert _step(conn, tid)["manual_review_required"] == 1
        assert kb.apply_workflow_human_event(conn, tid, "approve_done")
        row = _step(conn, tid)
        assert (row["status"], row["current_step_key"]) == ("done", "verified")


def test_human_gates_mode_pauses_and_gate_action_resumes(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        tid = kb.create_task(
            conn, title="careful one", workflow="aif", auto_mode=False,
        )
        assert kb.complete_task(conn, tid, result="plan done")
        row = _step(conn, tid)
        assert (row["status"], row["current_step_key"]) == ("blocked", "plan_ready")
        assert row["block_kind"] == "needs_input"
        assert not kb.unblock_task(conn, tid)
        assert kb.apply_workflow_human_event(conn, tid, "start_implementation")
        row = _step(conn, tid)
        assert (row["status"], row["current_step_key"], row["assignee"]) == (
            "ready", "implementing", "aif_implementer",
        )


def test_respawn_guard_exempts_workflow_stage_transitions(kanban_home: Path) -> None:
    """A completed stage run must NOT defer the next stage's spawn.

    check_respawn_guard's recent_success rule exists for classic cards
    (completed run + ready = a human re-readied something — wait). On a
    workflow card a completed run IS the stage handoff; guarding it
    stalled every stage transition for the whole guard window.
    """
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="ship it", workflow="aif")
        # simulate the planner run: claim → complete (stage advances)
        assert kb.claim_task(conn, tid, claimer="aif_planner") is not None
        assert kb.complete_task(conn, tid, result="plan done")
        row = _step(conn, tid)
        assert (row["status"], row["current_step_key"]) == ("ready", "implementing")
        # the freshly-completed run must not guard the implementing spawn
        assert kb.check_respawn_guard(conn, tid) is None

        # classic card: same sequence DOES guard (regression check)
        classic = kb.create_task(conn, title="classic", assignee="worker")
        assert kb.claim_task(conn, classic, claimer="worker") is not None
        assert kb.complete_task(conn, classic, result="done")
        with kb.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET status='ready', claim_lock=NULL, "
                "claim_expires=NULL WHERE id=?", (classic,),
            )
        assert kb.check_respawn_guard(conn, classic) == "recent_success"


def test_non_workflow_tasks_complete_normally(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        tid = kb.create_task(conn, title="plain card", assignee="worker")
        assert kb.complete_task(conn, tid, result="done")
        assert _step(conn, tid)["status"] == "done"


def test_use_subagents_precedence_task_beats_board_beats_config(
    kanban_home: Path,
) -> None:
    with kb.connect_closing() as conn:
        # default (no task/board/config value) → True (quality mode)
        tid = kb.create_task(conn, title="a", workflow="aif")
        assert kb.resolve_use_subagents(conn, tid) is True
        ctx = kb.build_worker_context(conn, tid)
        assert "Delegation mode: **subagents**" in ctx

        # board.json override
        kb.write_board_metadata(kb.get_current_board(), use_subagents=False)
        assert kb.resolve_use_subagents(conn, tid) is False
        assert "Delegation mode: **skills**" in kb.build_worker_context(conn, tid)

        # per-task column beats the board override
        tid2 = kb.create_task(
            conn, title="b", workflow="aif", use_subagents=True,
        )
        assert kb.resolve_use_subagents(conn, tid2) is True


def test_dependency_block_preserves_stage(kanban_home: Path) -> None:
    with kb.connect_closing() as conn:
        parent = kb.create_task(conn, title="dep", assignee="worker")
        tid = kb.create_task(
            conn, title="ship it", workflow="aif", workflow_step="implementing",
        )
        with kb.write_txn(conn):
            conn.execute(
                "INSERT OR IGNORE INTO task_links (parent_id, child_id) "
                "VALUES (?, ?)", (parent, tid),
            )
        assert kb.block_task(conn, tid, reason="waiting", kind="dependency")
        row = _step(conn, tid)
        assert row["status"] == "todo"
        assert row["current_step_key"] == "implementing"
