"""Telegram busy-session control regressions."""

from unittest.mock import AsyncMock, sentinel

import pytest

from plugins.platforms.telegram.adapter import TelegramAdapter


@pytest.mark.asyncio
async def test_edit_message_preserves_busy_keyboard_on_non_final_progress_edit():
    """Progress edits must include reply_markup for the active busy-control anchor.

    Telegram removes an inline keyboard when edit_message_text omits reply_markup.
    The tool-progress bubble is edited repeatedly with finalize=False, so omitting
    the busy keyboard here can briefly strand controls on a separate queue ack and
    produce duplicate-looking interrupt surfaces.
    """
    adapter = object.__new__(TelegramAdapter)
    adapter._bot = type("Bot", (), {})()
    adapter._bot.edit_message_text = AsyncMock()
    adapter._busy_session_button_map = {"session-1": "42"}
    adapter.MAX_MESSAGE_LENGTH = 4096
    adapter._build_busy_session_keyboard = lambda session_key: sentinel.busy_keyboard

    result = await TelegramAdapter.edit_message(
        adapter,
        chat_id="123",
        message_id="42",
        content="tool progress",
        finalize=False,
    )

    assert result.success is True
    adapter._bot.edit_message_text.assert_awaited_once()
    kwargs = adapter._bot.edit_message_text.await_args.kwargs
    assert kwargs["reply_markup"] is sentinel.busy_keyboard


@pytest.mark.asyncio
async def test_edit_message_does_not_add_busy_keyboard_to_unanchored_progress_edit():
    adapter = object.__new__(TelegramAdapter)
    adapter._bot = type("Bot", (), {})()
    adapter._bot.edit_message_text = AsyncMock()
    adapter._busy_session_button_map = {"session-1": "99"}
    adapter.MAX_MESSAGE_LENGTH = 4096
    adapter._build_busy_session_keyboard = lambda session_key: sentinel.busy_keyboard

    result = await TelegramAdapter.edit_message(
        adapter,
        chat_id="123",
        message_id="42",
        content="tool progress",
        finalize=False,
    )

    assert result.success is True
    kwargs = adapter._bot.edit_message_text.await_args.kwargs
    assert "reply_markup" not in kwargs
