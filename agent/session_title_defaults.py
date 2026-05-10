"""Deterministic fallback titles for sessions that need an immediate name."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

_TELEGRAM_FALLBACK_RE = re.compile(
    r"^Telegram [A-Z][a-z]{2} \d{1,2} \d{2}:\d{2} [0-9a-f]{4,8}$"
)
_SESSION_ID_TS_RE = re.compile(r"^(\d{8})_(\d{6})_")
_SESSION_SUFFIX_RE = re.compile(r"[A-Za-z0-9]+")
_MONTH_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _timestamp_from_session_id(session_id: str) -> Optional[datetime]:
    match = _SESSION_ID_TS_RE.match(session_id or "")
    if not match:
        return None
    try:
        return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _session_suffix(session_id: str, length: int = 8) -> str:
    tail = (session_id or "").rsplit("_", 1)[-1]
    cleaned = "".join(_SESSION_SUFFIX_RE.findall(tail)).lower()
    if cleaned:
        return cleaned[:length]
    return "session"


def telegram_fallback_title(session_id: str, created_at: Optional[datetime] = None) -> str:
    """Return a short deterministic title for a Telegram gateway session.

    The title is immediately useful in `/resume` and unique in normal Hermes
    session IDs because it includes the short random suffix.
    """
    dt = created_at or _timestamp_from_session_id(session_id) or datetime.now()
    month = _MONTH_ABBR[dt.month - 1]
    return f"Telegram {month} {dt.day} {dt:%H:%M} {_session_suffix(session_id)}"


def fallback_title_for_gateway_session(
    platform: object,
    session_id: str,
    created_at: Optional[datetime] = None,
) -> Optional[str]:
    """Return an immediate fallback title for platforms that need one."""
    value = getattr(platform, "value", platform)
    if str(value or "").lower() == "telegram":
        return telegram_fallback_title(session_id, created_at=created_at)
    return None


def is_generated_fallback_title(title: Optional[str]) -> bool:
    """Whether a title is one of Hermes' deterministic fallback names."""
    return bool(title and _TELEGRAM_FALLBACK_RE.match(title.strip()))
