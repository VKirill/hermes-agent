import json
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from agent.agy_cli_client import AgyCLIClient


def _write_fake_agy(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_agy.py"
    script.write_text(body, encoding="utf-8")
    return script


def _config(tmp_path: Path, **overrides):
    config = {
        "state_dir": str(tmp_path / "state"),
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
import sys
print(json.dumps({
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "has_google_key": "GOOGLE_API_KEY" in os.environ,
    "has_gemini_key": "GEMINI_API_KEY" in os.environ,
}))
""",
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-reach-child")
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
    assert argv[argv.index("--model") + 1] == "Gemini 3.5 Flash (Low)"
    assert argv[argv.index("--print-timeout") + 1] == "5s"
    assert "--sandbox" in argv
    assert argv[argv.index("--mode") + 1] == "plan"
    assert payload["has_google_key"] is False
    assert payload["has_gemini_key"] is False
    assert Path(payload["cwd"]).parent == tmp_path / "state" / "workspaces"
    events = client.read_log(response.agy_request_id)
    assert [event["event"] for event in events] == ["start", "success"]
    log_path = Path(response.agy_log_path)
    assert log_path.exists()
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600


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

    monkeypatch.setattr("agent.agy_cli_client.subprocess.run", timeout)
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
