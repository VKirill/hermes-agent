"""Tests for outgoing Telegram album grouping in the standalone send path.

Before this feature, ``_send_telegram`` looped over ``media_files`` and sent
each image via ``send_photo`` — ten photos in one ``send_message`` call
arrived as ten separate Telegram messages. Now two or more still images are
bundled into ``sendMediaGroup`` chunks (max 10 per album) so they arrive as a
single slider, mirroring what the gateway's final-response delivery path
(``send_multiple_images``) already did.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeInputMediaPhoto:
    def __init__(self, media):
        self.media = media


def _install_telegram_mock(monkeypatch: pytest.MonkeyPatch, bot: MagicMock) -> None:
    parse_mode = SimpleNamespace(MARKDOWN_V2="MarkdownV2", HTML="HTML")
    constants_mod = SimpleNamespace(ParseMode=parse_mode)
    _MessageEntity = lambda **_kw: SimpleNamespace(**_kw)  # noqa: E731
    telegram_mod = SimpleNamespace(
        Bot=MagicMock(return_value=bot),
        MessageEntity=_MessageEntity,
        InputMediaPhoto=_FakeInputMediaPhoto,
        constants=constants_mod,
    )
    monkeypatch.setitem(sys.modules, "telegram", telegram_mod)
    monkeypatch.setitem(sys.modules, "telegram.constants", constants_mod)


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=1))
    bot.send_photo = AsyncMock(return_value=SimpleNamespace(message_id=2))
    bot.send_document = AsyncMock(return_value=SimpleNamespace(message_id=3))
    bot.send_media_group = AsyncMock(
        return_value=[SimpleNamespace(message_id=10), SimpleNamespace(message_id=11)]
    )
    return bot


def _write_images(tmp_path, count: int, ext: str = ".jpg") -> list:
    paths = []
    for i in range(count):
        p = tmp_path / f"img_{i}{ext}"
        p.write_bytes(b"\xff\xd8fake")
        paths.append(str(p))
    return paths


def _run_send(monkeypatch, bot, media_files, **kwargs):
    monkeypatch.delenv("TELEGRAM_PROXY", raising=False)
    _install_telegram_mock(monkeypatch, bot)
    from tools.send_message_tool import _send_telegram

    return asyncio.run(
        _send_telegram(
            "123:token", "259034221", "", media_files=media_files, **kwargs
        )
    )


class TestTelegramOutgoingAlbums:
    def test_multiple_images_sent_as_one_media_group(self, monkeypatch, tmp_path):
        bot = _make_bot()
        paths = _write_images(tmp_path, 3)
        _run_send(monkeypatch, bot, [(p, False) for p in paths])

        assert bot.send_media_group.await_count == 1
        media = bot.send_media_group.await_args.kwargs["media"]
        assert len(media) == 3
        bot.send_photo.assert_not_awaited()

    def test_more_than_ten_images_chunked(self, monkeypatch, tmp_path):
        bot = _make_bot()
        paths = _write_images(tmp_path, 12)
        _run_send(monkeypatch, bot, [(p, False) for p in paths])

        assert bot.send_media_group.await_count == 2
        sizes = [len(c.kwargs["media"]) for c in bot.send_media_group.await_args_list]
        assert sizes == [10, 2]
        bot.send_photo.assert_not_awaited()

    def test_single_image_keeps_send_photo(self, monkeypatch, tmp_path):
        bot = _make_bot()
        paths = _write_images(tmp_path, 1)
        _run_send(monkeypatch, bot, [(p, False) for p in paths])

        bot.send_media_group.assert_not_awaited()
        assert bot.send_photo.await_count == 1

    def test_documents_not_grouped(self, monkeypatch, tmp_path):
        bot = _make_bot()
        paths = _write_images(tmp_path, 2)
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"%PDF fake")
        _run_send(
            monkeypatch, bot, [(p, False) for p in paths] + [(str(pdf), False)]
        )

        assert bot.send_media_group.await_count == 1
        assert len(bot.send_media_group.await_args.kwargs["media"]) == 2
        assert bot.send_document.await_count == 1

    def test_force_document_skips_grouping(self, monkeypatch, tmp_path):
        bot = _make_bot()
        paths = _write_images(tmp_path, 3)
        _run_send(
            monkeypatch, bot, [(p, False) for p in paths], force_document=True
        )

        bot.send_media_group.assert_not_awaited()
        assert bot.send_document.await_count == 3

    def test_gif_stays_on_per_file_path(self, monkeypatch, tmp_path):
        bot = _make_bot()
        jpgs = _write_images(tmp_path, 2)
        gifs = _write_images(tmp_path, 1, ext=".gif")
        _run_send(
            monkeypatch, bot, [(p, False) for p in jpgs + gifs]
        )

        assert bot.send_media_group.await_count == 1
        assert len(bot.send_media_group.await_args.kwargs["media"]) == 2
        # GIF goes through the legacy loop (send_photo path for .gif)
        assert bot.send_photo.await_count == 1

    def test_group_failure_falls_back_to_per_file(self, monkeypatch, tmp_path):
        bot = _make_bot()
        bot.send_media_group = AsyncMock(side_effect=RuntimeError("boom"))
        paths = _write_images(tmp_path, 3)
        _run_send(monkeypatch, bot, [(p, False) for p in paths])

        assert bot.send_media_group.await_count == 1
        assert bot.send_photo.await_count == 3

    def test_thread_id_passed_to_media_group(self, monkeypatch, tmp_path):
        bot = _make_bot()
        paths = _write_images(tmp_path, 2)
        _run_send(
            monkeypatch, bot, [(p, False) for p in paths], thread_id="919312"
        )

        kwargs = bot.send_media_group.await_args.kwargs
        assert kwargs.get("message_thread_id") == 919312
