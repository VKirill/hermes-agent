from pathlib import Path


def test_hermes_dev_gate_result_skill_documents_contract():
    skill = Path("skills/software-development/hermes-dev-gate-result/SKILL.md").read_text()

    assert skill.startswith("---\n")
    assert "name: hermes-dev-gate-result" in skill
    assert "schema_version" in skill
    assert '"gate": "verify"' in skill
    assert "kanban_complete" in skill
    assert "kanban_block" in skill
    assert "spec`, `verify`, `review`, `security`, `rules`, `qa`" in skill
