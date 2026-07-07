"""Tests for Telegram inline keyboard clarify buttons.

Mirrors test_telegram_approval_buttons.py for the new ``send_clarify`` and
``cl:`` callback dispatch added in feat/clarify-gateway-buttons.
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the repo root is importable
# ---------------------------------------------------------------------------
_repo = str(Path(__file__).resolve().parents[2])
if _repo not in sys.path:
    sys.path.insert(0, _repo)


# ---------------------------------------------------------------------------
# Minimal Telegram mock so TelegramAdapter can be imported (mirrors
# test_telegram_approval_buttons.py)
# ---------------------------------------------------------------------------
def _ensure_telegram_mock():
    if "telegram" in sys.modules and hasattr(sys.modules["telegram"], "__file__"):
        return

    mod = MagicMock()
    mod.ext.ContextTypes.DEFAULT_TYPE = type(None)
    mod.constants.ParseMode.MARKDOWN = "Markdown"
    mod.constants.ParseMode.MARKDOWN_V2 = "MarkdownV2"
    mod.constants.ParseMode.HTML = "HTML"
    mod.constants.ChatType.PRIVATE = "private"
    mod.constants.ChatType.GROUP = "group"
    mod.constants.ChatType.SUPERGROUP = "supergroup"
    mod.constants.ChatType.CHANNEL = "channel"
    mod.error.NetworkError = type("NetworkError", (OSError,), {})
    mod.error.TimedOut = type("TimedOut", (OSError,), {})
    mod.error.BadRequest = type("BadRequest", (Exception,), {})

    for name in ("telegram", "telegram.ext", "telegram.constants", "telegram.request"):
        sys.modules.setdefault(name, mod)
    sys.modules.setdefault("telegram.error", mod.error)


_ensure_telegram_mock()

from plugins.platforms.telegram.adapter import TelegramAdapter
from gateway.config import PlatformConfig


def _make_adapter(extra=None):
    config = PlatformConfig(enabled=True, token="test-token", extra=extra or {})
    adapter = TelegramAdapter(config)
    adapter._bot = AsyncMock()
    adapter._app = MagicMock()
    return adapter


def _clear_clarify_state():
    from tools import clarify_gateway as cm
    with cm._lock:
        cm._entries.clear()
        cm._session_index.clear()
        cm._notify_cbs.clear()


# ===========================================================================
# send_clarify — render
# ===========================================================================

class TestTelegramSendClarify:
    """Verify the rendered prompt has buttons or none, and stores state."""

    def setup_method(self):
        _clear_clarify_state()

    @pytest.mark.asyncio
    async def test_multi_choice_renders_buttons_and_other(self):
        adapter = _make_adapter()
        mock_msg = MagicMock()
        mock_msg.message_id = 100
        adapter._bot.send_message = AsyncMock(return_value=mock_msg)

        result = await adapter.send_clarify(
            chat_id="12345",
            question="Which option?",
            choices=["alpha", "beta", "gamma"],
            clarify_id="cid1",
            session_key="sk1",
        )

        assert result.success is True
        assert result.message_id == "100"

        kwargs = adapter._bot.send_message.call_args[1]
        assert kwargs["chat_id"] == 12345
        assert "Which option?" in kwargs["text"]
        # Short labels (≤24 chars) → text buttons, no numbered list in body
        assert "1. alpha" not in kwargs["text"]
        # InlineKeyboardMarkup with N+1 buttons (3 choices + Other)
        markup = kwargs["reply_markup"]
        assert markup is not None
        # Mocked InlineKeyboardMarkup — just verify it was constructed
        # with rows.  We check state instead of poking the mock structure.
        assert "cid1" in adapter._clarify_state
        assert adapter._clarify_state["cid1"] == "sk1"

    @pytest.mark.asyncio
    async def test_open_ended_no_keyboard(self):
        adapter = _make_adapter()
        mock_msg = MagicMock()
        mock_msg.message_id = 101
        adapter._bot.send_message = AsyncMock(return_value=mock_msg)

        result = await adapter.send_clarify(
            chat_id="12345",
            question="What is your name?",
            choices=None,
            clarify_id="cid2",
            session_key="sk2",
        )

        assert result.success is True
        kwargs = adapter._bot.send_message.call_args[1]
        # No reply_markup means no buttons — open-ended path
        assert "reply_markup" not in kwargs
        assert "What is your name?" in kwargs["text"]
        assert adapter._clarify_state["cid2"] == "sk2"

    @pytest.mark.asyncio
    async def test_not_connected(self):
        adapter = _make_adapter()
        adapter._bot = None
        result = await adapter.send_clarify(
            chat_id="12345",
            question="?",
            choices=["a"],
            clarify_id="cid3",
            session_key="sk3",
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_long_choice_rendered_in_body_not_truncated(self):
        """Long choice text appears in full in the message body;
        button labels stay short numeric (1, 2, …)."""
        adapter = _make_adapter()
        mock_msg = MagicMock()
        mock_msg.message_id = 102
        adapter._bot.send_message = AsyncMock(return_value=mock_msg)

        long_choice = "x" * 200
        result = await adapter.send_clarify(
            chat_id="12345",
            question="?",
            choices=[long_choice],
            clarify_id="cid4",
            session_key="sk4",
        )
        assert result.success is True
        kwargs = adapter._bot.send_message.call_args[1]
        # The full long choice text appears in the message body
        assert long_choice in kwargs["text"]
        # The button label should be short ("1"), not the long choice
        # (we can't inspect mock button labels directly, but the send
        # succeeded — old truncation code could raise on edge cases)

    @pytest.mark.asyncio
    async def test_html_escapes_question(self):
        adapter = _make_adapter()
        mock_msg = MagicMock()
        mock_msg.message_id = 103
        adapter._bot.send_message = AsyncMock(return_value=mock_msg)

        await adapter.send_clarify(
            chat_id="12345",
            question="<script>alert(1)</script>",
            choices=["x"],
            clarify_id="cid5",
            session_key="sk5",
        )
        kwargs = adapter._bot.send_message.call_args[1]
        # Must NOT contain raw <script> — html.escape should have neutralized
        assert "<script>" not in kwargs["text"]
        assert "&lt;script&gt;" in kwargs["text"]

    @pytest.mark.asyncio
    async def test_short_labels_use_text_buttons(self):
        """When ALL choice labels are ≤ 24 chars, buttons show label text
        directly and the message body has no numbered list."""
        adapter = _make_adapter()
        mock_msg = MagicMock()
        mock_msg.message_id = 200
        adapter._bot.send_message = AsyncMock(return_value=mock_msg)

        result = await adapter.send_clarify(
            chat_id="12345",
            question="Pick one",
            choices=["🌱 Plant rescue", "✈️ Travel parser", "🎨 Art gen"],
            clarify_id="cid-short",
            session_key="sk-short",
        )
        assert result.success is True
        kwargs = adapter._bot.send_message.call_args[1]
        # No numbered list in body for short labels
        assert "1. " not in kwargs["text"]
        assert "2. " not in kwargs["text"]
        assert "Pick one" in kwargs["text"]

    @pytest.mark.asyncio
    async def test_mixed_labels_use_numeric_buttons(self):
        """When ANY choice label exceeds 24 chars, fall back to numeric
        buttons and render the numbered list in the body."""
        adapter = _make_adapter()
        mock_msg = MagicMock()
        mock_msg.message_id = 201
        adapter._bot.send_message = AsyncMock(return_value=mock_msg)

        result = await adapter.send_clarify(
            chat_id="12345",
            question="Pick one",
            choices=["short", "x" * 25, "tiny"],
            clarify_id="cid-mixed",
            session_key="sk-mixed",
        )
        assert result.success is True
        kwargs = adapter._bot.send_message.call_args[1]
        # Numbered list in body for long labels
        assert "1. short" in kwargs["text"]
        assert "2. " in kwargs["text"]

    @pytest.mark.asyncio
    async def test_exactly_24_char_label_uses_text_buttons(self):
        """Labels exactly at the 24-char boundary use text buttons."""
        adapter = _make_adapter()
        mock_msg = MagicMock()
        mock_msg.message_id = 202
        adapter._bot.send_message = AsyncMock(return_value=mock_msg)

        result = await adapter.send_clarify(
            chat_id="12345",
            question="Choose",
            choices=["a" * 24],
            clarify_id="cid-exact",
            session_key="sk-exact",
        )
        assert result.success is True
        kwargs = adapter._bot.send_message.call_args[1]
        # Exactly 24 chars → text buttons, no numbered list
        assert "1. " not in kwargs["text"]


# ===========================================================================
# Callback dispatch — _handle_callback_query routing for cl:* prefixes
# ===========================================================================

class TestTelegramClarifyCallback:
    """Verify clicking a button resolves the clarify primitive."""

    def setup_method(self):
        _clear_clarify_state()

    @pytest.mark.asyncio
    async def test_numeric_choice_resolves_with_choice_text(self):
        from tools import clarify_gateway as cm

        adapter = _make_adapter()
        # Pre-register a clarify entry so the callback can look up the choice text
        cm.register("cidA", "sk-cb", "Pick", ["red", "green", "blue"])
        adapter._clarify_state["cidA"] = "sk-cb"

        query = AsyncMock()
        query.data = "cl:cidA:1"  # green
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.message.text = "Pick"
        query.from_user = MagicMock()
        query.from_user.id = "777"
        query.from_user.first_name = "Tester"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False):
            await adapter._handle_callback_query(update, context)

        # State popped
        assert "cidA" not in adapter._clarify_state
        # Wait shouldn't be needed — resolve_gateway_clarify is sync.
        # The entry's response should be set.
        # We test by reading the entry's response directly.
        with cm._lock:
            entry = cm._entries.get("cidA")
        # Entry might be popped by wait_for_response, but here we never
        # called wait — so it's still in _entries with response set.
        assert entry is not None
        assert entry.response == "green"
        assert entry.event.is_set()
        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_other_button_flips_to_text_mode(self):
        from tools import clarify_gateway as cm

        adapter = _make_adapter()
        cm.register("cidB", "sk-cb-other", "Pick", ["x", "y"])
        adapter._clarify_state["cidB"] = "sk-cb-other"

        query = AsyncMock()
        query.data = "cl:cidB:other"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.message.text = "Pick"
        query.from_user = MagicMock()
        query.from_user.id = "777"
        query.from_user.first_name = "Tester"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False):
            await adapter._handle_callback_query(update, context)

        # Entry should now be in text-capture mode
        pending = cm.get_pending_for_session("sk-cb-other")
        assert pending is not None
        assert pending.clarify_id == "cidB"
        assert pending.awaiting_text is True
        # State NOT popped — the user still needs to type their answer
        assert "cidB" in adapter._clarify_state
        # Entry NOT yet resolved
        with cm._lock:
            entry = cm._entries.get("cidB")
        assert entry is not None
        assert not entry.event.is_set()

    @pytest.mark.asyncio
    async def test_already_resolved(self):
        adapter = _make_adapter()
        # No state for cidGone

        query = AsyncMock()
        query.data = "cl:cidGone:0"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.from_user = MagicMock()
        query.from_user.id = "777"
        query.from_user.first_name = "Tester"
        query.answer = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False):
            await adapter._handle_callback_query(update, context)

        query.answer.assert_called_once()
        # Should NOT resolve anything
        assert "already" in query.answer.call_args[1]["text"].lower()

    @pytest.mark.asyncio
    async def test_unauthorized_user_rejected(self):
        from tools import clarify_gateway as cm

        adapter = _make_adapter()
        cm.register("cidC", "sk-auth", "Pick", ["a", "b"])
        adapter._clarify_state["cidC"] = "sk-auth"

        # Hook up a runner that says NOT authorized
        class _DenyRunner:
            async def _handle_message(self, event):
                return None
            def _is_user_authorized(self, source):
                return False

        adapter._message_handler = _DenyRunner()._handle_message

        query = AsyncMock()
        query.data = "cl:cidC:0"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.message.chat.type = "private"
        query.message.text = "Pick"
        query.from_user = MagicMock()
        query.from_user.id = "999"
        query.from_user.first_name = "Mallory"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        await adapter._handle_callback_query(update, context)

        # Must not resolve, must answer with not-authorized message
        with cm._lock:
            entry = cm._entries.get("cidC")
        assert entry is not None
        assert not entry.event.is_set()
        query.answer.assert_called_once()
        assert "not authorized" in query.answer.call_args[1]["text"].lower()
        # State preserved
        assert adapter._clarify_state["cidC"] == "sk-auth"

    @pytest.mark.asyncio
    async def test_numeric_choice_expired_notifies_user(self):
        """Late tap after the entry was evicted (timeout) or the gateway
        restarted must surface an expiry notice, not a misleading ✓."""
        adapter = _make_adapter()
        # _clarify_state still maps the id (timeout eviction does not pop it),
        # but the clarify primitive entry is gone → resolve returns False.
        adapter._clarify_state["cidExpired"] = "sk-expired"

        query = AsyncMock()
        query.data = "cl:cidExpired:0"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.message.text = "Pick"
        query.from_user = MagicMock()
        query.from_user.id = "777"
        query.from_user.first_name = "Tester"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False):
            await adapter._handle_callback_query(update, context)

        # User is told the prompt expired — not a misleading checkmark.
        answer_text = query.answer.call_args[1]["text"].lower()
        assert "expired" in answer_text
        edit_text = query.edit_message_text.call_args[1]["text"].lower()
        assert "expired" in edit_text or "session reset" in edit_text
        assert "/retry" in edit_text

    @pytest.mark.asyncio
    async def test_other_button_expired_notifies_user(self):
        """Tapping 'Other' after the entry was evicted must tell the user the
        prompt expired instead of silently entering text-capture mode."""
        adapter = _make_adapter()
        # No clarify primitive entry → mark_awaiting_text returns False.
        adapter._clarify_state["cidOtherExpired"] = "sk-other-expired"

        query = AsyncMock()
        query.data = "cl:cidOtherExpired:other"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.message.text = "Pick"
        query.from_user = MagicMock()
        query.from_user.id = "777"
        query.from_user.first_name = "Tester"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False):
            await adapter._handle_callback_query(update, context)

        answer_text = query.answer.call_args[1]["text"].lower()
        assert "expired" in answer_text
        # State popped so a subsequent typed message is not mis-captured.
        assert "cidOtherExpired" not in adapter._clarify_state

    @pytest.mark.asyncio
    async def test_invalid_choice_token(self):
        from tools import clarify_gateway as cm

        adapter = _make_adapter()
        cm.register("cidD", "sk-inv", "Q?", ["a"])
        adapter._clarify_state["cidD"] = "sk-inv"

        query = AsyncMock()
        query.data = "cl:cidD:not-a-number"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.message.text = "Q?"
        query.from_user = MagicMock()
        query.from_user.id = "777"
        query.from_user.first_name = "Tester"
        query.answer = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False):
            await adapter._handle_callback_query(update, context)

        with cm._lock:
            entry = cm._entries.get("cidD")
        assert entry is not None
        assert not entry.event.is_set()
        query.answer.assert_called_once()
        assert "invalid" in query.answer.call_args[1]["text"].lower()


# ===========================================================================
# Base adapter fallback render — text numbered list
# ===========================================================================

class TestBaseAdapterClarifyFallback:
    """Adapters without button overrides should render numbered text."""

    @pytest.mark.asyncio
    async def test_numbered_text_fallback(self):
        from gateway.platforms.base import BasePlatformAdapter, SendResult

        # Subclass just enough to instantiate
        class _Stub(BasePlatformAdapter):
            name = "stub"

            def __init__(self):
                # Skip base __init__ — we're not exercising it
                self.sent: list = []

            async def connect(self, *, is_reconnect: bool = False): pass
            async def disconnect(self): pass
            async def send(self, chat_id, content, **kw):
                self.sent.append({"chat_id": chat_id, "content": content})
                return SendResult(success=True, message_id="1")
            async def edit(self, *a, **k): return SendResult(success=False)
            async def get_history(self, *a, **k): return []
            async def get_chat_info(self, *a, **k): return {}

        adapter = _Stub()

        result = await adapter.send_clarify(
            chat_id="c",
            question="Pick a fruit",
            choices=["apple", "banana"],
            clarify_id="x",
            session_key="s",
        )
        assert result.success is True
        assert len(adapter.sent) == 1
        text = adapter.sent[0]["content"]
        assert "Pick a fruit" in text
        assert "1." in text and "apple" in text
        assert "2." in text and "banana" in text

    @pytest.mark.asyncio
    async def test_open_ended_fallback_renders_question_only(self):
        from gateway.platforms.base import BasePlatformAdapter, SendResult

        class _Stub(BasePlatformAdapter):
            name = "stub"
            def __init__(self):
                self.sent: list = []
            async def connect(self, *, is_reconnect: bool = False): pass
            async def disconnect(self): pass
            async def send(self, chat_id, content, **kw):
                self.sent.append(content)
                return SendResult(success=True, message_id="1")
            async def edit(self, *a, **k): return SendResult(success=False)
            async def get_history(self, *a, **k): return []
            async def get_chat_info(self, *a, **k): return {}

        adapter = _Stub()
        await adapter.send_clarify(
            chat_id="c",
            question="Free form?",
            choices=None,
            clarify_id="x",
            session_key="s",
        )
        assert "Free form?" in adapter.sent[0]
        # No numbered list — choices were empty
        assert "1." not in adapter.sent[0]


# ===========================================================================
# Pagination — >6 choices get 6 buttons per page + ◀ ▶ nav row
# ===========================================================================

class TestTelegramClarifyPagination:
    def setup_method(self):
        _clear_clarify_state()

    def test_single_page_has_no_nav(self):
        adapter = _make_adapter()
        captured = []

        import plugins.platforms.telegram.adapter as tg_mod
        orig_btn = tg_mod.InlineKeyboardButton
        orig_markup = tg_mod.InlineKeyboardMarkup

        class Btn:
            def __init__(self, label, callback_data=None):
                self.label = label
                self.callback_data = callback_data

        class Markup:
            def __init__(self, rows):
                captured.append(rows)

        tg_mod.InlineKeyboardButton = Btn
        tg_mod.InlineKeyboardMarkup = Markup
        try:
            adapter._clarify_page_view("cidP0", "Pick", ["a", "b", "c"], 0)
        finally:
            tg_mod.InlineKeyboardButton = orig_btn
            tg_mod.InlineKeyboardMarkup = orig_markup

        rows = captured[0]
        # 3 choice rows + Other row; no nav row for a single page
        assert len(rows) == 4
        assert rows[-1][0].callback_data == "cl:cidP0:other"
        labels = [r[0].label for r in rows[:3]]
        assert labels == ["a", "b", "c"]

    def test_pagination_first_page(self):
        adapter = _make_adapter()
        choices = [f"choice {i}" for i in range(1, 14)]  # 13 → 3 pages
        captured = []

        import plugins.platforms.telegram.adapter as tg_mod
        orig_btn = tg_mod.InlineKeyboardButton
        orig_markup = tg_mod.InlineKeyboardMarkup

        class Btn:
            def __init__(self, label, callback_data=None):
                self.label = label
                self.callback_data = callback_data

        class Markup:
            def __init__(self, rows):
                captured.append(rows)

        tg_mod.InlineKeyboardButton = Btn
        tg_mod.InlineKeyboardMarkup = Markup
        try:
            text, markup = adapter._clarify_page_view("cidP1", "Pick", choices, 0)
        finally:
            tg_mod.InlineKeyboardButton = orig_btn
            tg_mod.InlineKeyboardMarkup = orig_markup

        rows = captured[0]
        # 6 short-label buttons (one per row) + nav row + Other row = 8 rows
        assert len(rows) == 8
        # First six buttons carry GLOBAL indices 0..5
        first_labels = [r[0].label for r in rows[:6]]
        assert first_labels == [f"choice {i}" for i in range(1, 7)]
        assert [r[0].callback_data for r in rows[:6]] == [
            f"cl:cidP1:{i}" for i in range(6)
        ]
        # Nav row: no ◀ on first page; indicator 1/3; ▶ to page 1
        nav = rows[6]
        assert [b.label for b in nav] == ["1/3", "▶️"]
        assert nav[-1].callback_data == "cl:cidP1:pg:1"
        # Other row last
        assert rows[7][0].callback_data == "cl:cidP1:other"

    def test_pagination_last_page_global_indices(self):
        adapter = _make_adapter()
        choices = [f"choice {i}" for i in range(1, 14)]  # 13 → 3 pages
        captured = []

        import plugins.platforms.telegram.adapter as tg_mod
        orig_btn = tg_mod.InlineKeyboardButton
        orig_markup = tg_mod.InlineKeyboardMarkup

        class Btn:
            def __init__(self, label, callback_data=None):
                self.label = label
                self.callback_data = callback_data

        class Markup:
            def __init__(self, rows):
                captured.append(rows)

        tg_mod.InlineKeyboardButton = Btn
        tg_mod.InlineKeyboardMarkup = Markup
        try:
            text, markup = adapter._clarify_page_view("cidP2", "Pick", choices, 2)
        finally:
            tg_mod.InlineKeyboardButton = orig_btn
            tg_mod.InlineKeyboardMarkup = orig_markup

        rows = captured[0]
        # Last page: 1 choice (index 12) + nav + Other = 3 rows
        assert len(rows) == 3
        assert rows[0][0].callback_data == "cl:cidP2:12"
        nav = rows[1]
        # ◀ to page 1, indicator 3/3, no ▶
        assert [b.label for b in nav] == ["◀️", "3/3"]
        assert nav[0].callback_data == "cl:cidP2:pg:1"

    def test_page_clamped_out_of_range(self):
        adapter = _make_adapter()
        choices = [f"c{i}" for i in range(13)]
        # Should not raise on absurd page numbers
        adapter._clarify_page_view("cidP3", "Pick", choices, 99)
        adapter._clarify_page_view("cidP3", "Pick", choices, -5)

    @pytest.mark.asyncio
    async def test_nav_callback_edits_message_without_resolving(self):
        from tools import clarify_gateway as cm

        adapter = _make_adapter()
        choices = [f"choice {i}" for i in range(1, 14)]
        cm.register("cidNav", "sk-nav", "Pick", choices)
        adapter._clarify_state["cidNav"] = "sk-nav"

        query = AsyncMock()
        query.data = "cl:cidNav:pg:1"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.from_user = MagicMock()
        query.from_user.id = "777"
        query.from_user.first_name = "Tester"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False):
            await adapter._handle_callback_query(update, context)

        # Message edited in place, prompt NOT resolved, state kept
        query.edit_message_text.assert_called_once()
        assert "cidNav" in adapter._clarify_state
        with cm._lock:
            entry = cm._entries.get("cidNav")
        assert entry is not None
        assert not entry.event.is_set()

    @pytest.mark.asyncio
    async def test_nav_callback_on_expired_entry(self):
        adapter = _make_adapter()
        # No entry registered — simulates timeout eviction
        adapter._clarify_state["cidGone"] = "sk-gone"

        query = AsyncMock()
        query.data = "cl:cidGone:pg:1"
        query.message = MagicMock()
        query.message.chat_id = 12345
        query.from_user = MagicMock()
        query.from_user.id = "777"
        query.from_user.first_name = "Tester"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}, clear=False):
            await adapter._handle_callback_query(update, context)

        query.edit_message_text.assert_not_called()
        assert "cidGone" not in adapter._clarify_state
