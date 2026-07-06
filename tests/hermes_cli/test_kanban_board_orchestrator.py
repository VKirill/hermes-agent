"""Per-board orchestrator / default_assignee override precedence.

A board's ``board.json`` may pin its own ``orchestrator_profile`` /
``default_assignee``. That per-board value must beat the global
``kanban.*`` config so a dev board can be led by a dev profile while the
marketing board keeps its own lead. An empty/invalid override falls back
to the global config, then to the active default profile.
"""

import hermes_cli.kanban_decompose as kd


def test_board_override_beats_global_config(monkeypatch):
    monkeypatch.setattr(kd, "_profile_exists_and_not_deprecated", lambda name, dep: True)
    cfg = {"kanban": {"orchestrator_profile": "client_marketing",
                      "default_assignee": "client_marketing"}}
    assert kd._resolve_orchestrator_profile(cfg, set(), "aif_planner") == "aif_planner"
    assert kd._resolve_default_assignee(cfg, set(), "aif_planner") == "aif_planner"


def test_empty_board_override_falls_back_to_global(monkeypatch):
    monkeypatch.setattr(kd, "_profile_exists_and_not_deprecated", lambda name, dep: True)
    cfg = {"kanban": {"orchestrator_profile": "client_marketing",
                      "default_assignee": "client_marketing"}}
    assert kd._resolve_orchestrator_profile(cfg, set(), "") == "client_marketing"
    assert kd._resolve_default_assignee(cfg, set(), None) == "client_marketing"


def test_invalid_board_override_ignored(monkeypatch):
    # 'ghost' is not a real profile → override is ignored, global config wins.
    monkeypatch.setattr(kd, "_profile_exists_and_not_deprecated",
                        lambda name, dep: name != "ghost")
    cfg = {"kanban": {"orchestrator_profile": "client_marketing"}}
    assert kd._resolve_orchestrator_profile(cfg, set(), "ghost") == "client_marketing"
