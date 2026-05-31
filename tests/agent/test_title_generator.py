"""Tests for agent.title_generator — auto-generated session titles with icons."""

import json
from unittest.mock import MagicMock, patch

from agent.title_generator import (
    generate_title,
    auto_title_session,
    maybe_auto_title,
    _title_language,
)


def _json_response(title: str, icon: int = 1) -> MagicMock:
    """Build a mock LLM response returning JSON with title + icon."""
    mock = MagicMock()
    mock.choices = [MagicMock()]
    mock.choices[0].message.content = json.dumps({"title": title, "icon": icon})
    return mock


class TestGenerateTitle:
    """Unit tests for generate_title() — now returns (title, icon_id) tuple."""

    def test_returns_title_on_success(self):
        mock_response = _json_response("Debugging Python Import Errors", 1)
        with patch("agent.title_generator.call_llm", return_value=mock_response):
            title, icon_id = generate_title("help me fix this import", "Sure, let me check...")
            assert title == "Debugging Python Import Errors"
            assert icon_id is not None

    def test_default_prompt_matches_user_language(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Some Title"

        with patch("agent.title_generator.call_llm", return_value=mock_response) as llm:
            generate_title("質問です", "回答です")

        system_prompt = llm.call_args.kwargs["messages"][0]["content"]
        assert "same language the user is writing in" in system_prompt

    def test_configured_language_pins_prompt(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Some Title"

        with (
            patch("agent.title_generator.call_llm", return_value=mock_response) as llm,
            patch("agent.title_generator._title_language", return_value="Japanese"),
        ):
            generate_title("hello", "hi")

        system_prompt = llm.call_args.kwargs["messages"][0]["content"]
        assert "Write the title in Japanese" in system_prompt
        assert "same language the user" not in system_prompt

    def test_title_language_reads_config(self):
        cfg = {"auxiliary": {"title_generation": {"language": "  French "}}}

        with patch("hermes_cli.config.load_config", return_value=cfg):
            assert _title_language() == "French"
        with patch("hermes_cli.config.load_config", return_value={}):
            assert _title_language() == ""
        with patch("hermes_cli.config.load_config", side_effect=RuntimeError("bad config")):
            assert _title_language() == ""

    def test_strips_quotes(self):
        mock_response = _json_response('"Setting Up Docker Environment"', 4)
        with patch("agent.title_generator.call_llm", return_value=mock_response):
            title, icon_id = generate_title("how do I set up docker", "First install...")
            assert title == "Setting Up Docker Environment"
            assert icon_id is not None

    def test_strips_title_prefix(self):
        mock_response = _json_response("Title: Kubernetes Pod Debugging", 1)
        with patch("agent.title_generator.call_llm", return_value=mock_response):
            title, icon_id = generate_title("my pod keeps crashing", "Let me look...")
            assert title == "Kubernetes Pod Debugging"

    def test_truncates_long_titles(self):
        mock_response = _json_response("A" * 100, 1)
        with patch("agent.title_generator.call_llm", return_value=mock_response):
            title, icon_id = generate_title("question", "answer")
            assert title is not None
            assert len(title) == 80
            assert title.endswith("...")

    def test_returns_none_on_empty_response(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        with patch("agent.title_generator.call_llm", return_value=mock_response):
            title, icon_id = generate_title("question", "answer")
            assert title is None
            assert icon_id is None

    def test_returns_none_none_on_exception(self):
        with patch("agent.title_generator.call_llm", side_effect=RuntimeError("no provider")):
            title, icon_id = generate_title("question", "answer")
            assert title is None
            assert icon_id is None

    def test_invokes_failure_callback_on_exception(self):
        """failure_callback must fire so the user sees a warning (issue #15775)."""
        captured = []

        def _cb(task, exc):
            captured.append((task, exc))

        exc = RuntimeError("openrouter 402: credits exhausted")
        with patch("agent.title_generator.call_llm", side_effect=exc):
            title, icon_id = generate_title("question", "answer", failure_callback=_cb)

        assert title is None
        assert icon_id is None
        assert len(captured) == 1
        assert captured[0][0] == "title generation"
        assert captured[0][1] is exc

    def test_failure_callback_errors_are_swallowed(self):
        """A broken callback must not crash title generation."""
        def _bad_cb(task, exc):
            raise ValueError("callback bug")

        with patch("agent.title_generator.call_llm", side_effect=RuntimeError("nope")):
            title, icon_id = generate_title("q", "a", failure_callback=_bad_cb)
            assert title is None
            assert icon_id is None

    def test_no_callback_matches_legacy_behavior(self):
        """Omitting failure_callback preserves the silent-None return."""
        with patch("agent.title_generator.call_llm", side_effect=RuntimeError("nope")):
            title, icon_id = generate_title("q", "a")
            assert title is None
            assert icon_id is None

    def test_truncates_long_messages(self):
        """Long user/assistant messages should be truncated in the LLM request."""
        captured_kwargs = {}

        def mock_call_llm(**kwargs):
            captured_kwargs.update(kwargs)
            return _json_response("Short Title", 1)

        with patch("agent.title_generator.call_llm", side_effect=mock_call_llm):
            generate_title("x" * 1000, "y" * 1000)

        user_content = captured_kwargs["messages"][1]["content"]
        assert len(user_content) < 1100

    def test_invalid_json_returns_none(self):
        """Non-JSON LLM response should return (None, None)."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Just a plain string, not JSON"
        with patch("agent.title_generator.call_llm", return_value=mock_response):
            title, icon_id = generate_title("question", "answer")
            assert title is None
            assert icon_id is None

    def test_missing_title_field_returns_none(self):
        """JSON without 'title' key should return (None, None)."""
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = json.dumps({"icon": 3})
        with patch("agent.title_generator.call_llm", return_value=mock):
            title, icon_id = generate_title("question", "answer")
            assert title is None

    def test_out_of_range_icon_returns_none_icon(self):
        """Icon index outside 1-28 should yield icon_id=None."""
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = json.dumps({"title": "Valid Title", "icon": 999})
        with patch("agent.title_generator.call_llm", return_value=mock):
            title, icon_id = generate_title("question", "answer")
            assert title == "Valid Title"
            assert icon_id is None


class TestAutoTitleSession:
    """Tests for auto_title_session() — updated for title+icon tuple return."""

    def test_skips_if_no_session_db(self):
        auto_title_session(None, "sess-1", "hi", "hello")

    def test_skips_if_title_exists(self):
        db = MagicMock()
        db.get_session_title.return_value = "Existing Title"
        with patch("agent.title_generator.generate_title") as gen:
            auto_title_session(db, "sess-1", "hi", "hello")
            gen.assert_not_called()

    def test_replaces_generated_telegram_fallback_title(self):
        db = MagicMock()
        db.get_session_title.return_value = "Telegram May 10 12:38 deadbe"

        with patch("agent.title_generator.generate_title", return_value="DeFi Liquidation Searcher"):
            auto_title_session(db, "sess-1", "hi", "hello")

        db.set_session_title.assert_called_once_with("sess-1", "DeFi Liquidation Searcher")

    def test_generates_and_sets_title(self):
        db = MagicMock()
        db.get_session_title.return_value = None
        with patch("agent.title_generator.generate_title", return_value=("New Title", "emoji_123")):
            auto_title_session(db, "sess-1", "hi", "hello")
            db.set_session_title.assert_called_once_with("sess-1", "New Title")

    def test_invokes_title_callback_with_icon(self):
        db = MagicMock()
        db.get_session_title.return_value = None
        seen = []

        def two_arg_callback(title, icon_id=None):
            seen.append((title, icon_id))

        with patch("agent.title_generator.generate_title", return_value=("Readable Session", "emoji_456")):
            auto_title_session(
                db, "sess-1", "hello", "hi there",
                title_callback=two_arg_callback,
            )
        db.set_session_title.assert_called_once_with("sess-1", "Readable Session")
        assert seen == [("Readable Session", "emoji_456")]

    def test_backward_compat_one_arg_callback(self):
        """Legacy 1-arg callbacks still work — they just get the title."""
        db = MagicMock()
        db.get_session_title.return_value = None
        seen = []

        with patch("agent.title_generator.generate_title", return_value=("Title Only", "emoji_789")):
            auto_title_session(
                db, "sess-1", "hello", "hi there",
                title_callback=seen.append,
            )
        assert seen == ["Title Only"]

    def test_skips_if_generation_fails(self):
        db = MagicMock()
        db.get_session_title.return_value = None
        with patch("agent.title_generator.generate_title", return_value=(None, None)):
            auto_title_session(db, "sess-1", "hi", "hello")
            db.set_session_title.assert_not_called()


class TestMaybeAutoTitle:
    """Tests for maybe_auto_title() — fire-and-forget entry point."""

    def test_skips_if_not_first_exchange(self):
        db = MagicMock()
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "response 1"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "response 2"},
            {"role": "user", "content": "third"},
            {"role": "assistant", "content": "response 3"},
        ]
        with patch("agent.title_generator.auto_title_session") as mock_auto:
            maybe_auto_title(db, "sess-1", "third", "response 3", history)
            import time
            time.sleep(0.1)
            mock_auto.assert_not_called()

    def test_fires_on_first_exchange(self):
        db = MagicMock()
        db.get_session_title.return_value = None
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        with patch("agent.title_generator.auto_title_session") as mock_auto:
            maybe_auto_title(db, "sess-1", "hello", "hi there", history)
            import time
            time.sleep(0.3)
            mock_auto.assert_called_once_with(
                db, "sess-1", "hello", "hi there",
                failure_callback=None,
                main_runtime=None,
                title_callback=None,
            )

    def test_forwards_failure_callback_to_worker(self):
        db = MagicMock()
        db.get_session_title.return_value = None
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

        def _cb(task, exc):
            pass

        with patch("agent.title_generator.auto_title_session") as mock_auto:
            maybe_auto_title(db, "sess-1", "hello", "hi there", history, failure_callback=_cb)
            import time
            time.sleep(0.3)
            mock_auto.assert_called_once_with(
                db, "sess-1", "hello", "hi there",
                failure_callback=_cb,
                main_runtime=None,
                title_callback=None,
            )

    def test_skips_if_no_response(self):
        db = MagicMock()
        maybe_auto_title(db, "sess-1", "hello", "", [])

    def test_skips_if_no_session_db(self):
        maybe_auto_title(None, "sess-1", "hello", "response", [])
