import json
import os
import stat
import sys
from pathlib import Path

import pytest

from agent.agy_cli_client import AgyCLIClient


def _config():
    return {
        "timeout_seconds": 10,
        "queue_timeout_seconds": 10,
        "max_parallel": 1,
        "retry_budget": 0,
        "dedupe_ttl_seconds": 0,
        "sandbox": True,
        "mode": "plan",
        "max_log_bytes": 65536,
    }


def _write_negotiating_fake(tmp_path: Path, requested_target: Path) -> Path:
    script = tmp_path / "fake_scoped_agy.py"
    script.write_text(
        f"""
import json
import os
import sys
from pathlib import Path

argv = sys.argv[1:]
root = Path(next(item for item in argv if item.startswith('--gemini_dir=')).split('=', 1)[1])
settings = json.loads((root / 'antigravity-cli' / 'settings.json').read_text(encoding='utf-8'))
counter = Path({str(tmp_path / 'calls.txt')!r})
count = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(count))
target = Path({str(requested_target)!r})
write_rules = (settings.get('permissions') or {{}}).get('allow') or []
if not write_rules:
    transcript = root / 'antigravity-cli' / 'brain' / 'run' / '.system_generated' / 'logs' / 'transcript_full.jsonl'
    transcript.parent.mkdir(parents=True)
    transcript.write_text(json.dumps({{
        'tool_calls': [{{'name': 'write_to_file', 'args': {{'TargetFile': str(target)}}}}]
    }}) + '\\n', encoding='utf-8')
    print('I will create the requested file after permission is granted.')
    print('jetski: no output produced — a tool required the "write_file" permission that headless mode cannot prompt for, so it was auto-denied.', file=sys.stderr)
    raise SystemExit(0)
expected = f'write_file({{target.resolve(strict=False)}})'
assert write_rules == [expected], write_rules
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text('SCOPED_OK\\n', encoding='utf-8')
prompt_ref = argv[argv.index('-p') + 1]
prompt_path = Path(prompt_ref[1:])
print(json.dumps({{
    'cwd': os.getcwd(),
    'gemini_dir': str(root),
    'prompt_path': str(prompt_path),
    'prompt_mode': stat.S_IMODE(prompt_path.stat().st_mode) if False else 384,
    'write_rules': write_rules,
}}))
""",
        encoding="utf-8",
    )
    return script


def _client(monkeypatch, tmp_path: Path, workspace: Path, script: Path) -> AgyCLIClient:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile"))
    monkeypatch.setenv("HERMES_KANBAN_WORKSPACE", str(workspace))
    return AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(),
    )


def test_scoped_worker_write_negotiates_only_exact_target(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "probe.py"
    script = _write_negotiating_fake(tmp_path, target)
    client = _client(monkeypatch, tmp_path, workspace, script)

    response = client.chat.completions.create(
        model="Gemini 3.5 Flash (High)",
        messages=[{"role": "user", "content": f"Create {target}"}],
    )

    payload = json.loads(response.choices[0].message.content)
    assert target.read_text(encoding="utf-8") == "SCOPED_OK\n"
    assert (tmp_path / "calls.txt").read_text() == "1"
    assert Path(payload["cwd"]) == workspace.resolve()
    assert payload["write_rules"] == [f"write_file({target.resolve()})"]
    assert "write_file(*)" not in payload["write_rules"]
    assert not Path(payload["prompt_path"]).exists()
    runtime_root = Path(payload["gemini_dir"])
    assert runtime_root.parent == client._agy_config_root
    settings = json.loads(
        (runtime_root / "antigravity-cli" / "settings.json").read_text(encoding="utf-8")
    )
    assert settings["allowNonWorkspaceAccess"] is False
    assert settings["toolPermission"] == "request-review"
    assert settings["permissions"]["allow"] == [f"write_file({target.resolve()})"]
    project = json.loads(
        (
            runtime_root
            / "config"
            / "projects"
            / "default-cli-project.json"
        ).read_text(encoding="utf-8")
    )
    assert project["permissionGrants"]["permissionGrants"]["allow"] == [
        "read_file(*)",
        f"write_file({target.resolve()})",
    ]
    assert not (runtime_root / "antigravity-cli" / "hooks.json").exists()
    assert not (runtime_root / "antigravity-cli" / "mcp_config.json").exists()
    assert not (runtime_root / "antigravity-cli" / "plugins").exists()
    events = client.read_log(response.agy_request_id)
    assert [event["event"] for event in events] == [
        "start",
        "scoped_write_grant",
        "success",
    ]


def test_scoped_worker_write_rejects_outside_target(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    script = _write_negotiating_fake(tmp_path, outside)
    client = _client(monkeypatch, tmp_path, workspace, script)

    with pytest.raises(PermissionError, match="escapes worker workspace"):
        client.chat.completions.create(
            model="Gemini 3.5 Flash (High)",
            messages=[{"role": "user", "content": f"Write {outside}"}],
        )

    assert not outside.exists()
    assert not (tmp_path / "calls.txt").exists()


def test_scoped_worker_write_rejects_symlink_escape(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    link = workspace / "link"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    outside = outside_dir / "escape.py"
    script = _write_negotiating_fake(tmp_path, link / "escape.py")
    client = _client(monkeypatch, tmp_path, workspace, script)

    with pytest.raises(PermissionError, match="escapes worker workspace|symlink"):
        client.chat.completions.create(
            model="Gemini 3.5 Flash (High)",
            messages=[{"role": "user", "content": f"Write {link / 'escape.py'}"}],
        )

    assert not outside.exists()
    assert not (tmp_path / "calls.txt").exists()


def test_scoped_worker_write_does_not_reuse_stale_user_path(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "stale.py"
    script = _write_negotiating_fake(tmp_path, target)
    client = _client(monkeypatch, tmp_path, workspace, script)

    with pytest.raises(PermissionError, match="did not pre-authorize"):
        client.chat.completions.create(
            model="Gemini 3.5 Flash (High)",
            messages=[
                {"role": "user", "content": f"Create {target}"},
                {"role": "assistant", "content": "Understood."},
                {"role": "user", "content": "Now only explain the design."},
            ],
        )

    assert not target.exists()
    assert (tmp_path / "calls.txt").read_text() == "1"


def test_scoped_worker_write_rejects_existing_hardlink(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("ORIGINAL\n", encoding="utf-8")
    target = workspace / "linked.py"
    os.link(outside, target)
    script = _write_negotiating_fake(tmp_path, target)
    client = _client(monkeypatch, tmp_path, workspace, script)

    with pytest.raises(PermissionError, match="unsafe hardlinks"):
        client.chat.completions.create(
            model="Gemini 3.5 Flash (High)",
            messages=[{"role": "user", "content": f"Write {target}"}],
        )

    assert outside.read_text(encoding="utf-8") == "ORIGINAL\n"
    assert not (tmp_path / "calls.txt").exists()
