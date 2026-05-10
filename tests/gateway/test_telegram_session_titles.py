"""Telegram session title/resume behavior."""

from unittest.mock import MagicMock

import pytest

from gateway.config import GatewayConfig, Platform
from gateway.session import SessionSource, SessionStore


@pytest.mark.asyncio
async def test_restore_telegram_topic_accepts_generated_session_title(tmp_path):
    from gateway.run import GatewayRunner
    from hermes_state import SessionDB

    db = SessionDB(db_path=tmp_path / "state.db")
    target_session_id = "20260510_123000_deadbeef"
    target_title = "Telegram May 10 12:30 deadbe"
    db.create_session(target_session_id, "telegram", user_id="42")
    db.set_session_title(target_session_id, target_title)

    runner = GatewayRunner.__new__(GatewayRunner)
    runner._session_db = db
    runner.config = GatewayConfig()
    runner.session_store = SessionStore(tmp_path / "sessions", runner.config)
    runner.session_store._db = db

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="12345",
        chat_type="dm",
        user_id="42",
        thread_id="99",
    )
    event = MagicMock()
    event.source = source

    response = await runner._restore_telegram_topic_session(event, target_title)

    assert response.startswith(f"Session restored: {target_title}")
    binding = db.get_telegram_topic_binding(chat_id="12345", thread_id="99")
    assert binding is not None
    assert binding["session_id"] == target_session_id


@pytest.mark.asyncio
async def test_resume_by_title_inside_telegram_topic_rebinds_topic(tmp_path):
    from gateway.run import GatewayRunner
    from hermes_state import SessionDB

    db = SessionDB(db_path=tmp_path / "state.db")
    config = GatewayConfig()
    store = SessionStore(tmp_path / "sessions", config)
    store._db = db

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="12345",
        chat_type="dm",
        user_id="42",
        thread_id="99",
    )
    db.enable_telegram_topic_mode(chat_id="12345", user_id="42")
    current_entry = store.get_or_create_session(source)
    db.bind_telegram_topic(
        chat_id="12345",
        thread_id="99",
        user_id="42",
        session_key=current_entry.session_key,
        session_id=current_entry.session_id,
    )

    target_session_id = "20260510_123000_deadbeef"
    target_title = "Telegram May 10 12:30 deadbe"
    db.create_session(target_session_id, "telegram", user_id="42")
    db.set_session_title(target_session_id, target_title)

    runner = GatewayRunner.__new__(GatewayRunner)
    runner._session_db = db
    runner.config = config
    runner.session_store = store
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._busy_ack_ts = {}

    event = MagicMock()
    event.source = source
    event.get_command_args.return_value = target_title

    response = await runner._handle_resume_command(event)

    assert "Resumed session" in response
    assert target_title in response
    binding = db.get_telegram_topic_binding(chat_id="12345", thread_id="99")
    assert binding is not None
    assert binding["session_id"] == target_session_id
