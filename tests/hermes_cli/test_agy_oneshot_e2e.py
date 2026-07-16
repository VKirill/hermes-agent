import json
import os
import stat
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


class _FallbackSentinelHandler(BaseHTTPRequestHandler):
    hits: list[tuple[str, str]] = []

    def _record(self) -> None:
        type(self).hits.append((self.command, self.path))
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        self.send_response(500)
        self.end_headers()

    def do_GET(self) -> None:
        self._record()

    def do_POST(self) -> None:
        self._record()

    def log_message(self, format, *args) -> None:
        del format, args


def _write_failing_agy(tmp_path: Path) -> Path:
    if os.name == "nt":
        script = tmp_path / "agy.cmd"
        script.write_text("@exit /b 23\n", encoding="utf-8")
    else:
        script = tmp_path / "agy"
        script.write_text("#!/bin/sh\nexit 23\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_agy_oneshot_process_failure_exits_nonzero_without_gemini_fallback(tmp_path):
    """Exercise the real CLI path: process failures are not successful output."""
    fake_agy = _write_failing_agy(tmp_path)
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    state_dir = hermes_home / "cache" / "agy"
    sentinel = ThreadingHTTPServer(("127.0.0.1", 0), _FallbackSentinelHandler)
    thread = Thread(target=sentinel.serve_forever, daemon=True)
    _FallbackSentinelHandler.hits = []
    thread.start()
    try:
        (hermes_home / "config.yaml").write_text(
            "model:\n"
            "  provider: agy\n"
            "  default: Gemini 3.5 Flash (Low)\n"
            "fallback_providers:\n"
            "  - provider: gemini\n"
            "    model: gemini-sentinel\n"
            f"    base_url: http://127.0.0.1:{sentinel.server_port}/v1beta/openai\n"
            "agy:\n"
            f"  command: {fake_agy}\n"
            "  timeout_seconds: 5\n"
            "  queue_timeout_seconds: 5\n"
            "  max_parallel: 1\n"
            "  retry_budget: 0\n"
            "  dedupe_ttl_seconds: 0\n"
            f"  state_dir: {state_dir}\n"
            "  sandbox: true\n"
            "  mode: plan\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.update(
            {
                "HERMES_HOME": str(hermes_home),
                "GEMINI_API_KEY": "fallback-sentinel-key",
            }
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "hermes_cli.main",
                "--provider",
                "agy",
                "--model",
                "Gemini 3.5 Flash (Low)",
                "--oneshot",
                "hello",
            ],
            capture_output=True,
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            text=True,
            timeout=30,
        )
    finally:
        sentinel.shutdown()
        sentinel.server_close()
        thread.join(timeout=2)

    events = []
    for log_path in (state_dir / "logs").glob("*.jsonl"):
        events.extend(json.loads(line) for line in log_path.read_text().splitlines())

    assert completed.returncode != 0
    assert "API call failed after 1 retries" in completed.stdout
    assert _FallbackSentinelHandler.hits == []
    assert [event["event"] for event in events] == ["start", "failure"]
    assert events[-1]["kind"] == "exit_23"
    assert events[-1]["attempt"] == 1
