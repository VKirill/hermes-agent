"""Tests for deterministic gateway fallback session titles."""

from datetime import datetime

from agent.session_title_defaults import (
    is_generated_fallback_title,
    telegram_fallback_title,
)


def test_telegram_fallback_title_is_locale_independent_and_short():
    title = telegram_fallback_title(
        "20260203_040506_DEADBEEF",
        created_at=datetime(2026, 2, 3, 4, 5, 6),
    )

    assert title == "Telegram Feb 3 04:05 deadbeef"
    assert is_generated_fallback_title(title)


def test_non_generated_titles_are_not_placeholders():
    assert not is_generated_fallback_title("Telegram Research Session")
    assert not is_generated_fallback_title("Existing User Title")
