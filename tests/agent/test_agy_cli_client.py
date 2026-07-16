import asyncio
import json
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from agent.agy_cli_client import (
    AgyCLIClient,
    AsyncAgyCLIClient,
    _format_messages_as_prompt,
)


def _write_fake_agy(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_agy.py"
    script.write_text(body, encoding="utf-8")
    return script


def _config(tmp_path: Path, **overrides):
    config = {
        "timeout_seconds": 5,
        "queue_timeout_seconds": 5,
        "max_parallel": 1,
        "retry_budget": 0,
        "dedupe_ttl_seconds": 60,
        "sandbox": True,
        "mode": "plan",
        "max_log_bytes": 65536,
    }
    config.update(overrides)
    return config


def test_agy_client_uses_explicit_model_sanitized_env_isolated_cwd_and_logs(
    monkeypatch, tmp_path
):
    script = _write_fake_agy(
        tmp_path,
        """
import json
import os
import stat
import sys
argv = sys.argv[1:]
prompt_ref = argv[argv.index("-p") + 1]
assert prompt_ref.startswith("@")
prompt_path = prompt_ref[1:]
prompt = open(prompt_path, encoding="utf-8").read()
print(json.dumps({
    "argv": argv,
    "prompt": prompt,
    "prompt_path": prompt_path,
    "prompt_mode": stat.S_IMODE(os.stat(prompt_path).st_mode),
    "cwd": os.getcwd(),
    "has_google_key": "GOOGLE_API_KEY" in os.environ,
    "has_gemini_key": "GEMINI_API_KEY" in os.environ,
    "has_aws_access_key": "AWS_ACCESS_KEY_ID" in os.environ,
    "has_aws_secret_key": "AWS_SECRET_ACCESS_KEY" in os.environ,
    "has_aws_session_token": "AWS_SESSION_TOKEN" in os.environ,
    "has_claude_oauth_token": "CLAUDE_CODE_OAUTH_TOKEN" in os.environ,
}))
""",
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "must-not-reach-child")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-reach-child")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "must-not-reach-child")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "must-not-reach-child")
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path),
    )

    response = client.chat.completions.create(
        model="Gemini 3.5 Flash (Low)",
        messages=[{"role": "user", "content": "Return READY"}],
        timeout=float("inf"),
    )

    payload = json.loads(response.choices[0].message.content)
    argv = payload["argv"]
    assert "-p" in argv
    assert "Return READY" not in " ".join(argv)
    assert "Return READY" in payload["prompt"]
    assert argv[argv.index("--model") + 1] == "Gemini 3.5 Flash (Low)"
    assert argv[argv.index("--print-timeout") + 1] == "5s"
    assert "--sandbox" in argv
    assert argv[argv.index("--mode") + 1] == "plan"
    assert payload["has_google_key"] is False
    assert payload["has_gemini_key"] is False
    assert payload["has_aws_access_key"] is False
    assert payload["has_aws_secret_key"] is False
    assert payload["has_aws_session_token"] is False
    assert payload["has_claude_oauth_token"] is False
    assert Path(payload["cwd"]).parent == client._workspaces_dir
    prompt_path = Path(payload["prompt_path"])
    assert prompt_path.parent == Path(payload["cwd"])
    assert payload["prompt_mode"] == 0o600
    assert not prompt_path.exists()
    events = client.read_log(response.agy_request_id)
    assert [event["event"] for event in events] == ["start", "success"]
    log_path = Path(response.agy_log_path)
    assert log_path.exists()
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600


def test_agy_client_uses_hermetic_no_command_cli_config_without_changing_home(
    monkeypatch, tmp_path
):
    script = _write_fake_agy(
        tmp_path,
        """
import json
import os
import stat
import sys
argv = sys.argv[1:]
gemini_arg = next(item for item in argv if item.startswith("--gemini_dir="))
gemini_dir = gemini_arg.split("=", 1)[1]
settings_path = os.path.join(gemini_dir, "antigravity-cli", "settings.json")
project_path = os.path.join(gemini_dir, "config", "projects", "default-cli-project.json")
print(json.dumps({
    "argv": argv,
    "home": os.environ.get("HOME"),
    "gemini_dir": gemini_dir,
    "settings": json.load(open(settings_path, encoding="utf-8")),
    "project": json.load(open(project_path, encoding="utf-8")),
    "settings_mode": stat.S_IMODE(os.stat(settings_path).st_mode),
    "has_hooks": os.path.exists(os.path.join(gemini_dir, "antigravity-cli", "hooks.json")),
    "has_mcp": os.path.exists(os.path.join(gemini_dir, "antigravity-cli", "mcp_config.json")),
    "has_plugins": os.path.exists(os.path.join(gemini_dir, "antigravity-cli", "plugins")),
}))
""",
    )
    profile_home = tmp_path / "profile"
    login_home = tmp_path / "login-home"
    login_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(profile_home))
    monkeypatch.setenv("HOME", str(login_home))
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path),
    )
    # agy may persist runtime decisions after a prior launch. The adapter must
    # restore the managed policy immediately before every new process.
    (client._agy_config_root / "antigravity-cli" / "settings.json").write_text(
        '{"toolPermission":"always-proceed"}', encoding="utf-8"
    )
    (
        client._agy_config_root
        / "config"
        / "projects"
        / "default-cli-project.json"
    ).write_text(
        '{"id":"default-cli-project","name":"CLI Project"}', encoding="utf-8"
    )

    response = client.chat.completions.create(
        model="Gemini 3.5 Flash (Low)",
        messages=[{"role": "user", "content": "Return READY"}],
    )

    payload = json.loads(response.choices[0].message.content)
    gemini_dir = Path(payload["gemini_dir"])
    assert gemini_dir == client._agy_config_root
    assert gemini_dir.parent == client._state_dir
    assert payload["home"] == str(login_home)
    assert payload["argv"][payload["argv"].index("--project") + 1] == "default-cli-project"
    assert payload["settings"] == {
        "allowNonWorkspaceAccess": False,
        "artifactReviewPolicy": "asks-for-review",
        "toolPermission": "request-review",
        "trustedWorkspaces": [],
    }
    assert payload["project"]["permissionGrants"]["permissionGrants"] == {
        "allow": ["read_file(*)"],
        "ask": [],
        "deny": [],
    }
    assert payload["settings_mode"] == 0o600
    assert payload["has_hooks"] is False
    assert payload["has_mcp"] is False
    assert payload["has_plugins"] is False


def test_agy_client_rejects_symlinked_hermetic_settings(monkeypatch, tmp_path):
    profile_home = tmp_path / "profile"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))
    client = AgyCLIClient(agy_config=_config(tmp_path))
    settings_path = client._agy_config_root / "antigravity-cli" / "settings.json"
    outside = tmp_path / "outside-settings.json"
    outside.write_text('{"toolPermission":"always-proceed"}', encoding="utf-8")
    settings_path.unlink()
    settings_path.symlink_to(outside)

    with pytest.raises(PermissionError, match="symlink"):
        AgyCLIClient(agy_config=_config(tmp_path))
    assert outside.read_text(encoding="utf-8") == '{"toolPermission":"always-proceed"}'


def test_agy_client_uses_private_prompt_file_for_large_transcript(tmp_path):
    script = _write_fake_agy(
        tmp_path,
        """
import json
import os
import stat
import sys
argv = sys.argv[1:]
prompt_ref = argv[argv.index("-p") + 1]
assert prompt_ref.startswith("@")
prompt_path = prompt_ref[1:]
with open(prompt_path, encoding="utf-8") as handle:
    prompt = handle.read()
print(json.dumps({
    "argv": argv,
    "prompt_length": len(prompt),
    "prompt_path": prompt_path,
    "prompt_mode": stat.S_IMODE(os.stat(prompt_path).st_mode),
}))
""",
    )
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path),
    )
    marker = "LONG_TRANSCRIPT_SECRET"
    content = marker + ("x" * (2 * 1024 * 1024))

    response = client.chat.completions.create(
        model="Gemini 3.5 Flash (Low)",
        messages=[{"role": "user", "content": content}],
    )

    payload = json.loads(response.choices[0].message.content)
    assert payload["prompt_length"] > 2 * 1024 * 1024
    assert marker not in " ".join(payload["argv"])
    assert payload["prompt_mode"] == 0o600
    assert not Path(payload["prompt_path"]).exists()


def test_agy_client_runtime_cleanup_recovers_from_prompt_unlink_failure(
    monkeypatch, tmp_path
):
    script = _write_fake_agy(tmp_path, 'print("DONE")')
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path, dedupe_ttl_seconds=0),
    )
    original_unlink = Path.unlink

    def fail_prompt_unlink(path: Path, *args, **kwargs):
        if path.name.startswith("prompt-"):
            raise OSError("simulated prompt cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_prompt_unlink)

    response = client.chat.completions.create(
        model="Gemini 3.5 Flash (Low)",
        messages=[{"role": "user", "content": "cleanup"}],
    )

    assert response.choices[0].message.content == "DONE"
    assert list(client._workspaces_dir.iterdir()) == []


def test_agy_client_retries_nonzero_exit_within_budget(tmp_path):
    counter = tmp_path / "attempts.txt"
    script = _write_fake_agy(
        tmp_path,
        f"""
from pathlib import Path
import sys
counter = Path({str(counter)!r})
count = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(count))
if count == 1:
    print("temporary failure", file=sys.stderr)
    raise SystemExit(7)
print("RECOVERED")
""",
    )
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path, retry_budget=1, dedupe_ttl_seconds=0),
    )

    response = client.chat.completions.create(
        model="Gemini 3.5 Flash (Low)",
        messages=[{"role": "user", "content": "recover"}],
    )

    assert response.choices[0].message.content == "RECOVERED"
    assert counter.read_text() == "2"
    assert [event["event"] for event in client.read_log(response.agy_request_id)] == [
        "start",
        "failure",
        "retry",
        "start",
        "success",
    ]
    assert not list(client._workspaces_dir.rglob("prompt-*.txt"))


def test_agy_client_deduplicates_successful_requests_within_ttl(tmp_path):
    counter = tmp_path / "calls.txt"
    script = _write_fake_agy(
        tmp_path,
        f"""
from pathlib import Path
counter = Path({str(counter)!r})
count = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(count))
print(f"CALL-{{count}}")
""",
    )
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path),
    )
    kwargs = {
        "model": "Gemini 3.5 Flash (Low)",
        "messages": [{"role": "user", "content": "same request"}],
    }

    first = client.chat.completions.create(**kwargs)
    second = client.chat.completions.create(**kwargs)

    assert first.choices[0].message.content == "CALL-1"
    assert second.choices[0].message.content == "CALL-1"
    assert second.agy_cached is True
    assert counter.read_text() == "1"
    assert client.read_log(second.agy_request_id)[-1]["event"] == "cache_hit"


def test_agy_client_maps_tool_call_output_to_openai_contract(tmp_path):
    script = _write_fake_agy(
        tmp_path,
        """
import json
payload = {
    "id": "agy-call-1",
    "type": "function",
    "function": {
        "name": "probe_tool",
        "arguments": json.dumps({"value": "ping"}),
    },
}
print("<tool_call>" + json.dumps(payload) + "</tool_call>")
""",
    )
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path),
    )

    response = client.chat.completions.create(
        model="Gemini 3.5 Flash (Low)",
        messages=[{"role": "user", "content": "Call the probe tool"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "probe_tool",
                    "description": "Return a probe result.",
                    "parameters": {"type": "object"},
                },
            }
        ],
        tool_choice="auto",
    )

    choice = response.choices[0]
    assert choice.finish_reason == "tool_calls"
    assert choice.message.content == ""
    assert len(choice.message.tool_calls) == 1
    tool_call = choice.message.tool_calls[0]
    assert tool_call.id == "agy-call-1"
    assert tool_call.type == "function"
    assert tool_call.function.name == "probe_tool"
    assert json.loads(tool_call.function.arguments) == {"value": "ping"}


def test_agy_stream_uses_openai_delta_chunks(tmp_path):
    script = _write_fake_agy(tmp_path, 'print("STREAM-READY")')
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path),
    )

    chunks = list(
        client.chat.completions.create(
            model="Gemini 3.5 Flash (Low)",
            messages=[{"role": "user", "content": "stream"}],
            stream=True,
        )
    )

    assert chunks
    assert chunks[0].choices[0].delta.content == "STREAM-READY"
    assert chunks[0].choices[0].finish_reason == "stop"
    assert chunks[-1].choices == []
    assert chunks[-1].usage.total_tokens == 0


def test_agy_prompt_preserves_tool_call_history_metadata():
    prompt = _format_messages_as_prompt(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-history-1",
                        "type": "function",
                        "function": {
                            "name": "probe_tool",
                            "arguments": '{"value":"ping"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-history-1",
                "name": "probe_tool",
                "content": "TOOL-OK",
            },
        ],
        tools=None,
    )

    assert "call-history-1" in prompt
    assert "probe_tool" in prompt
    assert "value" in prompt
    assert "ping" in prompt
    assert "TOOL-OK" in prompt


def test_agy_close_stops_active_child_and_releases_lease(tmp_path):
    started = tmp_path / "started"
    script = _write_fake_agy(
        tmp_path,
        f"""
from pathlib import Path
import time
Path({str(started)!r}).write_text("started")
time.sleep(0.8)
print("LATE")
""",
    )
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path, dedupe_ttl_seconds=0),
    )
    errors: list[Exception] = []

    def run() -> None:
        try:
            client.chat.completions.create(
                model="Gemini 3.5 Flash (Low)",
                messages=[{"role": "user", "content": "wait"}],
            )
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.monotonic() + 2
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert started.exists()

    client.close()
    thread.join(timeout=0.2)
    stopped_by_close = not thread.is_alive()
    thread.join(timeout=2)

    assert stopped_by_close is True
    assert errors
    with client._connect_state() as conn:
        statuses = [row[0] for row in conn.execute("SELECT status FROM requests")]
    assert "running" not in statuses
    assert not list(client._workspaces_dir.rglob("prompt-*.txt"))


def test_async_agy_cancellation_stops_child_before_side_effect(tmp_path):
    started = tmp_path / "async-started"
    side_effect = tmp_path / "async-side-effect"
    script = _write_fake_agy(
        tmp_path,
        f"""
from pathlib import Path
import time
Path({str(started)!r}).write_text("started")
time.sleep(0.8)
Path({str(side_effect)!r}).write_text("should-not-exist")
print("LATE")
""",
    )
    sync_client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path, dedupe_ttl_seconds=0),
    )
    client = AsyncAgyCLIClient(sync_client)

    async def cancel_request() -> None:
        task = asyncio.create_task(
            client.chat.completions.create(
                model="Gemini 3.5 Flash (Low)",
                messages=[{"role": "user", "content": "cancel-me"}],
            )
        )
        deadline = asyncio.get_running_loop().time() + 2
        while not started.exists() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        assert started.exists()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_request())
    time.sleep(0.9)

    assert not side_effect.exists()
    with sync_client._connect_state() as conn:
        statuses = [row[0] for row in conn.execute("SELECT status FROM requests")]
    assert "running" not in statuses


def test_agy_close_stops_every_parallel_child(tmp_path):
    started_dir = tmp_path / "parallel-started"
    side_effect_dir = tmp_path / "parallel-side-effects"
    started_dir.mkdir()
    side_effect_dir.mkdir()
    script = _write_fake_agy(
        tmp_path,
        f"""
from pathlib import Path
import sys
import time
prompt_ref = sys.argv[sys.argv.index("-p") + 1]
prompt = Path(prompt_ref[1:]).read_text()
name = "one" if "parallel-one" in prompt else "two"
Path({str(started_dir)!r}, name).write_text("started")
if name == "one":
    deadline = time.monotonic() + 2
    while not Path({str(started_dir)!r}, "two").exists() and time.monotonic() < deadline:
        time.sleep(0.01)
else:
    time.sleep(0.8)
    Path({str(side_effect_dir)!r}, name).write_text("should-not-exist")
print(name)
""",
    )
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path, max_parallel=2, dedupe_ttl_seconds=0),
    )
    errors: list[Exception] = []
    results: list[str] = []

    def run(name: str) -> None:
        try:
            response = client.chat.completions.create(
                model="Gemini 3.5 Flash (Low)",
                messages=[{"role": "user", "content": f"parallel-{name}"}],
            )
            results.append(response.choices[0].message.content)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(name,)) for name in ("one", "two")]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 2
    while len(list(started_dir.iterdir())) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(list(started_dir.iterdir())) == 2
    threads[0].join(timeout=2)
    assert threads[0].is_alive() is False
    assert threads[1].is_alive() is True

    client.close()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert results == ["one"]
    assert len(errors) == 1
    assert list(side_effect_dir.iterdir()) == []


def test_agy_clients_share_a_cross_process_concurrency_limit(tmp_path):
    script = _write_fake_agy(
        tmp_path,
        """
import time
time.sleep(0.4)
print("DONE")
""",
    )
    config = _config(tmp_path, dedupe_ttl_seconds=0)
    clients = [
        AgyCLIClient(command=sys.executable, args=[str(script)], agy_config=config)
        for _ in range(2)
    ]
    start = threading.Event()
    results = []

    def run(index):
        start.wait()
        results.append(
            clients[index].chat.completions.create(
                model="Gemini 3.5 Flash (Low)",
                messages=[{"role": "user", "content": f"request-{index}"}],
            )
        )

    threads = [threading.Thread(target=run, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    started = time.monotonic()
    start.set()
    for thread in threads:
        thread.join(timeout=5)
    elapsed = time.monotonic() - started

    assert all(item.choices[0].message.content == "DONE" for item in results)
    assert elapsed >= 0.7


def test_agy_client_bounds_timeout_retries_and_fails_closed(monkeypatch, tmp_path):
    calls = 0

    def timeout(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise __import__("subprocess").TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr("agent.agy_cli_client._run_bounded_process", timeout)
    client = AgyCLIClient(
        command="agy",
        agy_config=_config(tmp_path, timeout_seconds=1, retry_budget=1),
    )

    with pytest.raises(TimeoutError, match="after 2 attempt"):
        client.chat.completions.create(
            model="Gemini 3.5 Flash (Low)",
            messages=[{"role": "user", "content": "timeout"}],
        )

    assert calls == 2


def test_agy_client_rejects_symlinked_state_and_workspace(monkeypatch, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    profile_home = tmp_path / "profile"
    (profile_home / "cache").mkdir(parents=True)
    state_link = profile_home / "cache" / "agy"
    state_link.symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    with pytest.raises(PermissionError, match="symlink"):
        AgyCLIClient(agy_config=_config(tmp_path))

    state_link.unlink()
    script = _write_fake_agy(tmp_path, 'print("SHOULD-NOT-RUN")')
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path),
    )
    messages = [{"role": "user", "content": "workspace symlink"}]
    prompt = _format_messages_as_prompt(messages, tools=None)
    request_id = client._request_id(model="Gemini 3.5 Flash (Low)", prompt=prompt)
    workspace = client._workspaces_dir / request_id
    workspace.symlink_to(outside, target_is_directory=True)

    with pytest.raises(PermissionError, match="symlink"):
        client.chat.completions.create(
            model="Gemini 3.5 Flash (Low)", messages=messages
        )


def test_agy_client_rejects_symlinked_database_and_log(monkeypatch, tmp_path):
    outside_db = tmp_path / "outside.sqlite3"
    outside_db.write_bytes(b"outside-db")
    profile_home = tmp_path / "profile"
    state = profile_home / "cache" / "agy"
    state.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(profile_home))
    (state / "state.sqlite3").symlink_to(outside_db)

    with pytest.raises(OSError):
        AgyCLIClient(agy_config=_config(tmp_path))
    assert outside_db.read_bytes() == b"outside-db"

    (state / "state.sqlite3").unlink()
    sidecar = state / "state.sqlite3-journal"
    sidecar.symlink_to(outside_db)
    with pytest.raises(OSError):
        AgyCLIClient(agy_config=_config(tmp_path))
    assert outside_db.read_bytes() == b"outside-db"

    sidecar.unlink()
    client = AgyCLIClient(agy_config=_config(tmp_path))
    outside_log = tmp_path / "outside.log"
    outside_log.write_text("outside-log", encoding="utf-8")
    request_id = "b" * 24
    client._log_path(request_id).symlink_to(outside_log)

    with pytest.raises(OSError):
        client._append_log(request_id, {"event": "must-not-escape"})
    assert outside_log.read_text(encoding="utf-8") == "outside-log"


def test_agy_client_fails_closed_when_private_permissions_cannot_be_applied(
    monkeypatch, tmp_path
):
    original_chmod = __import__("os").chmod
    profile_home = tmp_path / "profile"
    state_dir = profile_home / "cache" / "agy"
    monkeypatch.setenv("HERMES_HOME", str(profile_home))

    def fail_state_chmod(path, mode, **kwargs):
        if Path(path) == state_dir:
            raise OSError("permission denied")
        return original_chmod(path, mode, **kwargs)

    monkeypatch.setattr("agent.agy_cli_client.os.chmod", fail_state_chmod)
    with pytest.raises(PermissionError, match="could not secure"):
        AgyCLIClient(agy_config=_config(tmp_path))


def test_agy_client_physically_bounds_output_logs_and_database(tmp_path):
    script = _write_fake_agy(
        tmp_path,
        'import sys\nsys.stdout.write("X" * 200_000)\n',
    )
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(
            tmp_path,
            max_output_bytes=4096,
            max_log_bytes=4096,
            max_db_bytes=65536,
            max_state_rows=8,
            dedupe_ttl_seconds=0,
        ),
    )

    with pytest.raises(RuntimeError, match="bounded stdout_limit capture"):
        client.chat.completions.create(
            model="Gemini 3.5 Flash (Low)",
            messages=[{"role": "user", "content": "large output"}],
        )

    log_files = list(client._logs_dir.glob("*.jsonl"))
    assert log_files
    assert all(path.stat().st_size <= 4096 for path in log_files)
    assert client._db_path.stat().st_size <= 65536
    with client._connect_state() as conn:
        status, response = conn.execute(
            "SELECT status, response FROM requests"
        ).fetchone()
    assert status == "failed"
    assert response is None

    request_id = "a" * 24
    for index in range(20):
        client._append_log(
            request_id,
            {"event": "probe", "index": index, "payload": "Y" * 1000},
        )
    assert client._log_path(request_id).stat().st_size <= 4096


def test_agy_client_serializes_concurrent_log_rotation(tmp_path):
    client = AgyCLIClient(
        agy_config=_config(tmp_path, max_log_bytes=4096)
    )
    request_id = "c" * 24
    gate = threading.Event()
    errors: list[Exception] = []

    def write_events(worker: int) -> None:
        gate.wait()
        try:
            for index in range(20):
                client._append_log(
                    request_id,
                    {
                        "event": "concurrent",
                        "worker": worker,
                        "index": index,
                        "payload": "Z" * 300,
                    },
                )
        except Exception as exc:  # pragma: no cover - assertion reports details
            errors.append(exc)

    threads = [threading.Thread(target=write_events, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    gate.set()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert all(not thread.is_alive() for thread in threads)
    assert client._log_path(request_id).stat().st_size <= 4096
    assert client.read_log(request_id)


def test_agy_client_cleans_old_and_excess_state_rows(tmp_path):
    client = AgyCLIClient(
        agy_config=_config(
            tmp_path,
            max_state_rows=8,
            state_ttl_seconds=60,
        )
    )
    now = time.time()
    with client._connect_state() as conn:
        for index in range(12):
            conn.execute(
                "INSERT INTO requests(request_id, status, started_at, finished_at) "
                "VALUES (?, 'success', ?, ?)",
                (f"{index:024x}", now - index, now - index),
            )
        conn.execute(
            "INSERT INTO requests(request_id, status, started_at, finished_at) "
            "VALUES (?, 'failed', ?, ?)",
            ("f" * 24, now - 120, now - 120),
        )
        client._cleanup_state_rows(conn)
        rows = conn.execute(
            "SELECT request_id FROM requests ORDER BY finished_at DESC"
        ).fetchall()

    assert len(rows) <= 8
    assert ("f" * 24,) not in rows


def test_agy_client_garbage_collects_stale_and_excess_workspaces(tmp_path):
    config = _config(
        tmp_path,
        max_state_rows=8,
        state_ttl_seconds=60,
    )
    client = AgyCLIClient(agy_config=config)
    workspaces = client._workspaces_dir
    now = time.time()
    stale = workspaces / ("f" * 24)
    stale.mkdir()
    stale.touch()
    __import__("os").utime(stale, (now - 120, now - 120))

    newest = workspaces / ("e" * 24)
    for index in range(12):
        workspace = workspaces / f"{index:024x}"
        workspace.mkdir()
        __import__("os").utime(workspace, (now - index, now - index))
    newest.mkdir()
    __import__("os").utime(newest, (now + 1, now + 1))
    with client._connect_state() as conn:
        conn.execute(
            "INSERT INTO requests(request_id, status, started_at, finished_at) "
            "VALUES (?, 'running', ?, NULL)",
            (newest.name, now),
        )

    AgyCLIClient(agy_config=config)

    retained = list(workspaces.iterdir())
    assert stale not in retained
    assert newest in retained
    assert retained == [newest]


def test_agy_client_bounds_workspaces_during_live_client_requests(tmp_path):
    script = _write_fake_agy(tmp_path, 'print("DONE")')
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(
            tmp_path,
            max_state_rows=8,
            dedupe_ttl_seconds=0,
        ),
    )

    for index in range(20):
        response = client.chat.completions.create(
            model="Gemini 3.5 Flash (Low)",
            messages=[{"role": "user", "content": f"unique-{index}"}],
        )
        assert response.choices[0].message.content == "DONE"

    assert len(list(client._workspaces_dir.iterdir())) <= 8


def test_agy_default_state_is_scoped_to_hermes_profile(monkeypatch, tmp_path):
    legacy_default = "~/.cache/hermes/agy"
    shared_override = tmp_path / "shared-state"
    first_home = tmp_path / "profile-a"
    second_home = tmp_path / "profile-b"
    monkeypatch.setenv("HERMES_HOME", str(first_home))
    first = AgyCLIClient(agy_config={"state_dir": str(shared_override)})
    monkeypatch.setenv("HERMES_HOME", str(second_home))
    second = AgyCLIClient(agy_config={"state_dir": legacy_default})

    assert first._state_dir == first_home / "cache" / "agy"
    assert second._state_dir == second_home / "cache" / "agy"
    assert first._state_dir != second._state_dir
    assert not shared_override.exists()


def test_agy_request_id_covers_execution_context(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile"))
    first = AgyCLIClient(command="agy")
    second = AgyCLIClient(command="agy-wrapper", args=["wrapper-config"])

    first_id = first._request_id(model="model", prompt="same")
    second_id = second._request_id(model="model", prompt="same")

    assert first_id != second_id


@pytest.mark.parametrize(
    "agy_config,args,error",
    [
        ({"sandbox": False}, None, "sandbox=true"),
        ({"mode": "accept-edits"}, None, "mode='plan'"),
        ({}, ["--dangerously-skip-permissions"], "managed by Hermes"),
        ({}, ["--gemini_dir=/tmp/escape"], "managed by Hermes"),
        ({}, ["--prompt-interactive"], "managed by Hermes"),
    ],
)
def test_agy_client_rejects_tool_policy_bypasses(tmp_path, agy_config, args, error):
    with pytest.raises(ValueError, match=error):
        AgyCLIClient(
            command="agy",
            args=args,
            agy_config=_config(tmp_path, **agy_config),
        )


def test_agy_client_redacts_stderr_before_log_and_error(monkeypatch, tmp_path):
    script = _write_fake_agy(
        tmp_path,
        """
import sys
print("SENSITIVE_CHILD_DIAGNOSTIC", file=sys.stderr)
raise SystemExit(9)
""",
    )
    monkeypatch.setattr(
        "agent.agy_cli_client._redact_process_text",
        lambda text: text.replace("SENSITIVE_CHILD_DIAGNOSTIC", "[REDACTED]"),
    )
    client = AgyCLIClient(
        command=sys.executable,
        args=[str(script)],
        agy_config=_config(tmp_path),
    )

    with pytest.raises(RuntimeError) as exc_info:
        client.chat.completions.create(
            model="Gemini 3.5 Flash (Low)",
            messages=[{"role": "user", "content": "fail safely"}],
        )

    assert "SENSITIVE_CHILD_DIAGNOSTIC" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)
    request_id = str(exc_info.value).split()[2]
    serialized = json.dumps(client.read_log(request_id))
    assert "SENSITIVE_CHILD_DIAGNOSTIC" not in serialized
    assert "[REDACTED]" in serialized


def test_agy_clients_dedupe_same_inflight_request(tmp_path):
    counter = tmp_path / "inflight.txt"
    script = _write_fake_agy(
        tmp_path,
        f"""
from pathlib import Path
import time
counter = Path({str(counter)!r})
count = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(count))
time.sleep(0.25)
print(f"RESULT-{{count}}")
""",
    )
    config = _config(tmp_path)
    clients = [
        AgyCLIClient(command=sys.executable, args=[str(script)], agy_config=config)
        for _ in range(2)
    ]
    gate = threading.Event()
    results = []

    def run(client):
        gate.wait()
        results.append(
            client.chat.completions.create(
                model="Gemini 3.5 Flash (Low)",
                messages=[{"role": "user", "content": "identical"}],
            )
        )

    threads = [threading.Thread(target=run, args=(client,)) for client in clients]
    for thread in threads:
        thread.start()
    gate.set()
    for thread in threads:
        thread.join(timeout=5)

    assert counter.read_text() == "1"
    assert [item.choices[0].message.content for item in results] == [
        "RESULT-1",
        "RESULT-1",
    ]
    assert sum(bool(item.agy_cached) for item in results) == 1
