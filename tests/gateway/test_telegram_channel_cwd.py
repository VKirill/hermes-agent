"""Telegram per-topic working directories (channel_cwds).

The Telegram adapter resolves ``channel_cwd`` with the same key scheme it
already used for ``channel_prompt``: exact match on the topic (thread) id
first, then the chat id as the parent fallback — so one chat-level entry
sets a default cwd for every topic while specific topics override it.
"""

from __future__ import annotations

from gateway.platforms.base import resolve_channel_cwd


def test_topic_id_exact_match(tmp_path):
    extra = {"channel_cwds": {"919312": str(tmp_path)}}
    assert resolve_channel_cwd(extra, "919312", "259034221") == str(tmp_path)


def test_chat_id_parent_fallback(tmp_path):
    extra = {"channel_cwds": {"259034221": str(tmp_path)}}
    assert resolve_channel_cwd(extra, "919312", "259034221") == str(tmp_path)


def test_topic_overrides_chat_default(tmp_path):
    topic_dir = tmp_path / "topic"
    chat_dir = tmp_path / "chat"
    topic_dir.mkdir()
    chat_dir.mkdir()
    extra = {"channel_cwds": {"919312": str(topic_dir), "259034221": str(chat_dir)}}
    assert resolve_channel_cwd(extra, "919312", "259034221") == str(topic_dir)


def test_no_match_returns_none(tmp_path):
    extra = {"channel_cwds": {"111": str(tmp_path)}}
    assert resolve_channel_cwd(extra, "919312", "259034221") is None


def test_missing_directory_ignored(tmp_path):
    extra = {"channel_cwds": {"919312": str(tmp_path / "does-not-exist")}}
    assert resolve_channel_cwd(extra, "919312", "259034221") is None


def test_tilde_expansion():
    extra = {"channel_cwds": {"919312": "~"}}
    resolved = resolve_channel_cwd(extra, "919312", None)
    assert resolved and not resolved.startswith("~")


def test_adapter_wires_channel_cwd_next_to_channel_prompt():
    """Regression guard: the MessageEvent construction site must pass both
    channel_prompt and channel_cwd (the cwd wiring was missing entirely
    before this feature — Discord/Mattermost had it, Telegram didn't)."""
    import inspect
    from plugins.platforms.telegram import adapter as tg

    src = inspect.getsource(tg)
    assert "resolve_channel_cwd" in src
    assert "channel_cwd=_channel_cwd" in src
