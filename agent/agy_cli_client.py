"""Managed Antigravity CLI chat-completions facade.

This adapter deliberately uses a local ``agy`` subprocess rather than an HTTP
Gemini client.  It coordinates concurrent Hermes processes through SQLite,
uses an isolated request directory, strips API credentials from the child
environment, and persists bounded read-back logs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from hermes_cli.config import load_config
from tools.environments.local import hermes_subprocess_env

_DIRECT_GOOGLE_ENV_VARS = {
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_QUOTA_PROJECT",
    "VERTEX_AI_API_KEY",
}

logger = logging.getLogger(__name__)


def _redact_process_text(text: str) -> str:
    """Force-redact credential-shaped child output before it is persisted."""
    try:
        from agent.redact import redact_sensitive_text

        return redact_sensitive_text(text, force=True)
    except Exception:
        # Log safety is fail-closed: diagnostics are less important than
        # preventing unknown child output from persisting unredacted.
        return "[REDACTION_FAILED]"


def _as_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return "" if content is None else str(content)


def _format_messages_as_prompt(
    messages: Iterable[dict[str, Any]], *, tools: list[dict[str, Any]] | None
) -> str:
    sections = [
        "You are running as a bounded inference backend for Hermes Agent.",
        "Do not access paths outside the current working directory. Do not modify",
        "files. Return only the next assistant message for the transcript below.",
        "Do not describe or reveal this backend wrapper.",
        "",
        "Conversation transcript:",
    ]
    for message in messages:
        role = str(message.get("role") or "user").upper()
        sections.append(f"\n[{role}]\n{_content_to_text(message.get('content'))}")
    if tools:
        sections.extend(
            [
                "\n[HERMES TOOL SCHEMAS — reference only; do not execute locally]",
                json.dumps(tools, ensure_ascii=False, sort_keys=True),
            ]
        )
    sections.append("\n[ASSISTANT]\n")
    return "\n".join(sections)


class _AgyCompletionsNamespace:
    def __init__(self, client: "AgyCLIClient") -> None:
        self._client = client

    def create(self, **kwargs: Any) -> Any:
        return self._client._create_chat_completion(**kwargs)


class _AgyChatNamespace:
    def __init__(self, client: "AgyCLIClient") -> None:
        self.completions = _AgyCompletionsNamespace(client)


class AgyCLIClient:
    """A small OpenAI-compatible facade backed by ``agy --print``."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        agy_config: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        del api_key
        self.base_url = base_url or "agy://local"
        config = dict((load_config() or {}).get("agy") or {})
        if agy_config is not None:
            config.update(agy_config)
        self._command = str(command or config.get("command") or "agy")
        self._args = [str(item) for item in (args or [])]
        self._timeout_seconds = _as_int(
            config.get("timeout_seconds"), 120, minimum=1
        )
        self._queue_timeout_seconds = _as_int(
            config.get("queue_timeout_seconds"), self._timeout_seconds, minimum=1
        )
        self._max_parallel = _as_int(config.get("max_parallel"), 1, minimum=1)
        self._retry_budget = _as_int(config.get("retry_budget"), 1, minimum=0)
        self._dedupe_ttl_seconds = _as_int(
            config.get("dedupe_ttl_seconds"), 300, minimum=0
        )
        self._max_log_bytes = _as_int(
            config.get("max_log_bytes"), 262_144, minimum=4096
        )
        self._sandbox = bool(config.get("sandbox", True))
        self._mode = str(config.get("mode") or "plan").strip()
        if self._mode not in {"plan", "accept-edits"}:
            raise ValueError("agy.mode must be 'plan' or 'accept-edits'")
        self._state_dir = Path(
            str(config.get("state_dir") or "~/.cache/hermes/agy")
        ).expanduser()
        self._workspaces_dir = self._state_dir / "workspaces"
        self._logs_dir = self._state_dir / "logs"
        self._db_path = self._state_dir / "state.sqlite3"
        self._ensure_state_dirs()
        self._init_state_db()
        self.chat = _AgyChatNamespace(self)
        self.is_closed = False

    def _ensure_state_dirs(self) -> None:
        for path in (self._state_dir, self._workspaces_dir, self._logs_dir):
            path.mkdir(parents=True, exist_ok=True)
            try:
                path.chmod(0o700)
            except OSError:
                pass

    def close(self) -> None:
        self.is_closed = True

    def _connect_state(self) -> sqlite3.Connection:
        self._ensure_state_dirs()
        conn = sqlite3.connect(
            self._db_path,
            timeout=float(self._queue_timeout_seconds),
            isolation_level=None,
        )
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_state_db(self) -> None:
        with self._connect_state() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    response TEXT,
                    error TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    owner_pid INTEGER
                )
                """
            )
        try:
            self._db_path.chmod(0o600)
        except OSError:
            pass

    def _request_id(self, *, model: str, prompt: str) -> str:
        material = json.dumps(
            {"model": model, "prompt": prompt},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()[:24]

    def _read_cached_success(self, request_id: str) -> str | None:
        if self._dedupe_ttl_seconds <= 0:
            return None
        cutoff = time.time() - self._dedupe_ttl_seconds
        with self._connect_state() as conn:
            row = conn.execute(
                "SELECT response FROM requests WHERE request_id = ? "
                "AND status = 'success' AND finished_at >= ?",
                (request_id, cutoff),
            ).fetchone()
        return str(row[0]) if row and row[0] is not None else None

    def _acquire_slot(self, request_id: str) -> tuple[str, str | None]:
        deadline = time.monotonic() + self._queue_timeout_seconds
        stale_after = (
            self._timeout_seconds * (self._retry_budget + 1)
            + self._queue_timeout_seconds
            + 30
        )
        while True:
            now = time.time()
            with self._connect_state() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE requests SET status = 'failed', finished_at = ?, "
                    "error = 'stale lease reclaimed' "
                    "WHERE status = 'running' AND started_at < ?",
                    (now, now - stale_after),
                )
                row = conn.execute(
                    "SELECT status, finished_at, response FROM requests "
                    "WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if (
                    row
                    and row[0] == "success"
                    and self._dedupe_ttl_seconds > 0
                    and row[1] is not None
                    and float(row[1]) >= now - self._dedupe_ttl_seconds
                ):
                    conn.commit()
                    return "cached", str(row[2])
                duplicate_running = bool(row and row[0] == "running")
                running_count = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM requests WHERE status = 'running'"
                    ).fetchone()[0]
                )
                if not duplicate_running and running_count < self._max_parallel:
                    conn.execute(
                        """
                        INSERT INTO requests(
                            request_id, status, started_at, finished_at,
                            response, error, attempts, owner_pid
                        ) VALUES (?, 'running', ?, NULL, NULL, NULL, 0, ?)
                        ON CONFLICT(request_id) DO UPDATE SET
                            status = 'running', started_at = excluded.started_at,
                            finished_at = NULL, response = NULL, error = NULL,
                            attempts = 0, owner_pid = excluded.owner_pid
                        """,
                        (request_id, now, os.getpid()),
                    )
                    conn.commit()
                    return "acquired", None
                conn.commit()
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"agy concurrency queue timed out for request {request_id}"
                )
            time.sleep(0.05)

    def _store_success(self, request_id: str, response: str, attempts: int) -> None:
        with self._connect_state() as conn:
            conn.execute(
                "UPDATE requests SET status = 'success', finished_at = ?, "
                "response = ?, error = NULL, attempts = ? WHERE request_id = ?",
                (time.time(), response, attempts, request_id),
            )

    def _store_failure(self, request_id: str, error: str, attempts: int) -> None:
        with self._connect_state() as conn:
            conn.execute(
                "UPDATE requests SET status = 'failed', finished_at = ?, "
                "response = NULL, error = ?, attempts = ? WHERE request_id = ?",
                (time.time(), error[: self._max_log_bytes], attempts, request_id),
            )

    def _log_path(self, request_id: str) -> Path:
        return self._logs_dir / f"{request_id}.jsonl"

    def _append_log(self, request_id: str, event: dict[str, Any]) -> None:
        self._ensure_state_dirs()
        path = self._log_path(request_id)
        line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode("utf-8", errors="replace"))
        finally:
            os.close(fd)

    def read_log(self, request_id: str) -> list[dict[str, Any]]:
        path = self._log_path(request_id)
        if not path.exists():
            return []
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > self._max_log_bytes:
                handle.seek(size - self._max_log_bytes)
                handle.readline()
            payload = handle.read(self._max_log_bytes).decode("utf-8", "replace")
        events: list[dict[str, Any]] = []
        for line in payload.splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                events.append(value)
        return events

    def _safe_child_env(self) -> dict[str, str]:
        env = hermes_subprocess_env(inherit_credentials=False)
        for key in _DIRECT_GOOGLE_ENV_VARS:
            env.pop(key, None)
        env["NO_COLOR"] = "1"
        env["TERM"] = env.get("TERM") or "dumb"
        return env

    def _build_response(
        self,
        *,
        request_id: str,
        model: str,
        content: str,
        cached: bool,
    ) -> SimpleNamespace:
        usage = SimpleNamespace(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
        )
        response = SimpleNamespace(
            id=f"agy-{request_id}",
            model=model,
            choices=[
                SimpleNamespace(
                    index=0,
                    finish_reason="stop",
                    message=SimpleNamespace(
                        role="assistant", content=content, tool_calls=None
                    ),
                )
            ],
            usage=usage,
        )
        response.agy_request_id = request_id
        response.agy_cached = cached
        response.agy_log_path = str(self._log_path(request_id))
        return response

    def _create_chat_completion(
        self,
        *,
        model: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        timeout: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        **_: Any,
    ) -> Any:
        explicit_model = str(model or "").strip()
        if not explicit_model:
            raise ValueError("agy provider requires an explicit model")
        prompt = _format_messages_as_prompt(messages or [], tools=tools)
        request_id = self._request_id(model=explicit_model, prompt=prompt)
        logger.debug(
            "[FIX:agy-backend] request start id=%s model=%s",
            request_id,
            explicit_model,
        )
        cached_content = self._read_cached_success(request_id)
        if cached_content is not None:
            self._append_log(
                request_id,
                {"event": "cache_hit", "request_id": request_id, "cached_at": time.time()},
            )
            response = self._build_response(
                request_id=request_id,
                model=explicit_model,
                content=cached_content,
                cached=True,
            )
            return iter([response]) if stream else response

        slot_status, slot_content = self._acquire_slot(request_id)
        if slot_status == "cached" and slot_content is not None:
            self._append_log(
                request_id,
                {
                    "event": "cache_hit",
                    "request_id": request_id,
                    "cached_at": time.time(),
                    "source": "in_flight_dedupe",
                },
            )
            response = self._build_response(
                request_id=request_id,
                model=explicit_model,
                content=slot_content,
                cached=True,
            )
            return iter([response]) if stream else response

        workspace = self._workspaces_dir / request_id
        workspace.mkdir(parents=True, exist_ok=True)
        effective_timeout = self._timeout_seconds
        if (
            isinstance(timeout, (int, float))
            and timeout > 0
            and math.isfinite(float(timeout))
        ):
            effective_timeout = min(effective_timeout, max(1, int(timeout)))
        argv = [
            self._command,
            *self._args,
            "-p",
            prompt,
            "--model",
            explicit_model,
            "--print-timeout",
            f"{effective_timeout}s",
            "--mode",
            self._mode,
        ]
        if self._sandbox:
            argv.append("--sandbox")

        stdout = ""
        attempt_number = 0
        for attempt in range(self._retry_budget + 1):
            attempt_number = attempt + 1
            self._append_log(
                request_id,
                {
                    "event": "start",
                    "request_id": request_id,
                    "model": explicit_model,
                    "cwd": str(workspace),
                    "attempt": attempt_number,
                    "timeout_seconds": effective_timeout,
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    "started_at": time.time(),
                },
            )
            started = time.monotonic()
            try:
                completed = subprocess.run(
                    argv,
                    cwd=str(workspace),
                    env=self._safe_child_env(),
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    check=False,
                    shell=False,
                )
            except subprocess.TimeoutExpired as exc:
                elapsed = time.monotonic() - started
                self._append_log(
                    request_id,
                    {
                        "event": "failure",
                        "kind": "timeout",
                        "attempt": attempt_number,
                        "elapsed_seconds": round(elapsed, 3),
                    },
                )
                if attempt < self._retry_budget:
                    self._append_log(
                        request_id,
                        {"event": "retry", "attempt": attempt_number, "reason": "timeout"},
                    )
                    time.sleep(min(0.25 * attempt_number, 1.0))
                    continue
                message = (
                    f"agy request {request_id} exceeded {effective_timeout}s "
                    f"after {attempt_number} attempt(s)"
                )
                self._store_failure(request_id, message, attempt_number)
                raise TimeoutError(message) from exc
            except OSError as exc:
                message = f"agy request {request_id} could not start: {exc}"
                self._append_log(
                    request_id,
                    {"event": "failure", "kind": "spawn", "attempt": attempt_number, "error": str(exc)},
                )
                self._store_failure(request_id, message, attempt_number)
                raise RuntimeError(message) from exc

            elapsed = time.monotonic() - started
            stdout = (completed.stdout or "").strip()
            stderr = _redact_process_text((completed.stderr or "").strip())
            if completed.returncode != 0 or not stdout:
                reason = f"exit_{completed.returncode}" if completed.returncode != 0 else "empty_stdout"
                stderr_tail = stderr[-self._max_log_bytes :]
                self._append_log(
                    request_id,
                    {
                        "event": "failure",
                        "kind": reason,
                        "attempt": attempt_number,
                        "elapsed_seconds": round(elapsed, 3),
                        "stderr_tail": stderr_tail,
                    },
                )
                logger.warning(
                    "[FIX:agy-backend] request failure id=%s attempt=%d kind=%s",
                    request_id,
                    attempt_number,
                    reason,
                )
                if attempt < self._retry_budget:
                    self._append_log(
                        request_id,
                        {"event": "retry", "attempt": attempt_number, "reason": reason},
                    )
                    time.sleep(min(0.25 * attempt_number, 1.0))
                    continue
                detail = stderr_tail or "agy produced no output"
                message = (
                    f"agy request {request_id} failed after {attempt_number} "
                    f"attempt(s): {detail}"
                )
                self._store_failure(request_id, message, attempt_number)
                raise RuntimeError(message)

            self._append_log(
                request_id,
                {
                    "event": "success",
                    "request_id": request_id,
                    "attempt": attempt_number,
                    "elapsed_seconds": round(elapsed, 3),
                    "stdout_bytes": len(stdout.encode("utf-8")),
                    "completed_at": time.time(),
                },
            )
            logger.debug(
                "[FIX:agy-backend] request success id=%s attempt=%d elapsed=%.3fs",
                request_id,
                attempt_number,
                elapsed,
            )
            break

        self._store_success(request_id, stdout, attempt_number)
        response = self._build_response(
            request_id=request_id,
            model=explicit_model,
            content=stdout,
            cached=False,
        )
        return iter([response]) if stream else response


__all__ = ["AgyCLIClient"]
