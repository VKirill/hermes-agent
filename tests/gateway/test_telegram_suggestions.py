"""Telegram suggestion buttons (send_suggestion + sg: callbacks).

Port of the Slack adapter's suggestion block: the base delivery pipeline
calls ``send_suggestion`` when a SUGGESTION:{...} marker is stripped from
the agent's response; buttons inject a synthetic internal message back
into the topic's session ("do"/"explain") or just remove themselves
("dismiss").
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig
from plugins.platforms.telegram import adapter as tg_adapter
from plugins.platforms.telegram.adapter import TelegramAdapter


class _FakeButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _FakeMarkup:
    def __init__(self, rows):
        self.inline_keyboard = rows


@pytest.fixture(autouse=True)
def _real_keyboard_classes(monkeypatch):
    """conftest ставит MagicMock вместо telegram — подменяем классы клавиатуры
    на простые фейки, чтобы структуру кнопок можно было инспектировать."""
    monkeypatch.setattr(tg_adapter, "InlineKeyboardButton", _FakeButton)
    monkeypatch.setattr(tg_adapter, "InlineKeyboardMarkup", _FakeMarkup)


def _make_adapter():
    config = PlatformConfig(enabled=True, token="fake-token", extra={})
    adapter = TelegramAdapter(config)
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=77))
    adapter._bot = bot
    return adapter


def _keyboard_labels(call):
    keyboard = call.kwargs["reply_markup"]
    return [b.text for row in keyboard.inline_keyboard for b in row]


def _keyboard_callbacks(call):
    keyboard = call.kwargs["reply_markup"]
    return [b.callback_data for row in keyboard.inline_keyboard for b in row]


class TestSendSuggestion:
    def test_sends_buttons_with_auto_execute(self):
        adapter = _make_adapter()
        result = asyncio.run(
            adapter.send_suggestion("259034221", "⚡ Next: опубликовать пост", can_auto_execute=True)
        )
        assert result.success is True
        call = adapter._bot.send_message.call_args
        assert _keyboard_callbacks(call) == ["sg:do", "sg:explain", "sg:dismiss"]

    def test_no_do_button_without_auto_execute(self):
        adapter = _make_adapter()
        asyncio.run(adapter.send_suggestion("259034221", "⚡ Next: проверить логи"))
        call = adapter._bot.send_message.call_args
        assert _keyboard_callbacks(call) == ["sg:explain", "sg:dismiss"]

    def test_thread_id_from_metadata(self):
        adapter = _make_adapter()
        asyncio.run(
            adapter.send_suggestion(
                "259034221", "⚡ Next: x", metadata={"thread_id": "919312"}
            )
        )
        call = adapter._bot.send_message.call_args
        assert call.kwargs.get("message_thread_id") == 919312

    def test_markdown_parse_error_falls_back_to_plain(self):
        adapter = _make_adapter()
        adapter._bot.send_message = AsyncMock(
            side_effect=[Exception("Bad Request: can't parse entities"), SimpleNamespace(message_id=78)]
        )
        result = asyncio.run(adapter.send_suggestion("259034221", "⚡ Next: a_b_c"))
        assert result.success is True
        assert adapter._bot.send_message.call_count == 2
        assert adapter._bot.send_message.call_args.kwargs["parse_mode"] is None


def _make_query(data, thread_id=919312, is_topic_message=True, message_id=555):
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=259034221, first_name="Kirill"),
        message=SimpleNamespace(
            chat_id=259034221,
            chat=SimpleNamespace(type="private"),
            message_thread_id=thread_id,
            is_topic_message=is_topic_message,
            message_id=message_id,
        ),
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )


def _run_callback(adapter, query):
    update = SimpleNamespace(callback_query=query)
    asyncio.run(adapter._handle_callback_query(update, None))


class TestSuggestionCallbacks:
    def test_do_injects_internal_message(self):
        adapter = _make_adapter()
        adapter._is_callback_user_authorized = MagicMock(return_value=True)
        adapter.handle_message = AsyncMock()
        query = _make_query("sg:do")

        _run_callback(adapter, query)

        adapter.handle_message.assert_awaited_once()
        event = adapter.handle_message.await_args.args[0]
        assert event.internal is True
        assert "следующий шаг" in event.text
        assert event.source.thread_id == "919312"
        # chat_type must be the normalized "dm" (not Telegram's raw "private"),
        # otherwise topic->profile binding and DM-topic delivery both miss and
        # the turn lands in the default profile/model and fails to deliver.
        assert event.source.chat_type == "dm"
        # the tapped suggestion message must be carried as the reply anchor so
        # DM-topic delivery is not refused ("requires a reply anchor").
        assert event.message_id == "555"
        assert event.source.message_id == "555"
        query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)

    def test_do_thread_falls_back_to_raw_when_not_topic_message(self):
        # Some callback message payloads omit is_topic_message; the raw
        # message_thread_id must still route the turn into the topic lane.
        adapter = _make_adapter()
        adapter._is_callback_user_authorized = MagicMock(return_value=True)
        adapter.handle_message = AsyncMock()

        _run_callback(adapter, _make_query("sg:do", is_topic_message=False))

        event = adapter.handle_message.await_args.args[0]
        assert event.source.thread_id == "919312"
        assert event.source.chat_type == "dm"

    def test_explain_injects_internal_message(self):
        adapter = _make_adapter()
        adapter._is_callback_user_authorized = MagicMock(return_value=True)
        adapter.handle_message = AsyncMock()

        _run_callback(adapter, _make_query("sg:explain"))

        event = adapter.handle_message.await_args.args[0]
        assert "Объясни" in event.text

    def test_dismiss_only_removes_buttons(self):
        adapter = _make_adapter()
        adapter._is_callback_user_authorized = MagicMock(return_value=True)
        adapter.handle_message = AsyncMock()
        query = _make_query("sg:dismiss")

        _run_callback(adapter, query)

        adapter.handle_message.assert_not_awaited()
        query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)

    def test_unauthorized_click_is_ignored(self):
        adapter = _make_adapter()
        adapter._is_callback_user_authorized = MagicMock(return_value=False)
        adapter.handle_message = AsyncMock()
        query = _make_query("sg:do")

        _run_callback(adapter, query)

        adapter.handle_message.assert_not_awaited()
        query.edit_message_reply_markup.assert_not_awaited()
