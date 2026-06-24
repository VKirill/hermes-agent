"""Parse suggestion markers from agent responses.

Detects a structured ``SUGGESTION:{...}`` marker that the LLM appends to
non-tactical responses. The gateway post-processor calls
``extract_suggestion()`` to strip the marker from the visible response text
and extract fields for interactive button delivery on platforms that support
it (Telegram, Slack).

Marker format:

    SUGGESTION:{"next": "Email Albert Shin", "reason": "CO expires Jul 15", "can_do": true}

Fields:
- ``next`` (str): the recommended user action
- ``learn`` (str): optional brief explanation of what Hermes just did
- ``reason`` (str): why this is the next step
- ``can_do`` (bool): whether Hermes is allowed to auto-execute this step

If the platform adapter lacks ``send_suggestion``, the marker is left in the
response text and rendered as plain text by the existing persona directive.
"""

import json
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Suggestion:
    """Structured suggestion extracted from an agent response."""
    next: Optional[str] = None
    learn: Optional[str] = None
    reason: Optional[str] = None
    can_do: bool = False
    raw_text: str = ""


_SUGGESTION_RE = re.compile(
    r"SUGGESTION:\s*(\{.*?\})\s*$",
    re.DOTALL,
)


def extract_suggestion(response_text: str) -> tuple[str, Optional[Suggestion]]:
    """Extract a SUGGESTION marker from the response text.

    Returns ``(cleaned_text, suggestion)``. If no valid marker is found,
    ``cleaned_text`` is the original input and ``suggestion`` is ``None``.
    """
    if not response_text or not response_text.strip():
        return response_text, None

    match = _SUGGESTION_RE.search(response_text)
    if not match:
        return response_text, None

    payload = match.group(1)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return response_text, None

    if not isinstance(data, dict):
        return response_text, None

    next_step = (data.get("next") or "").strip()
    learn_step = (data.get("learn") or "").strip()
    reason = (data.get("reason") or "").strip()
    can_do = bool(data.get("can_do", False))

    if not next_step and not learn_step:
        return response_text, None

    cleaned = response_text[: match.start()].rstrip()
    suggestion = Suggestion(
        next=next_step or None,
        learn=learn_step or None,
        reason=reason or None,
        can_do=can_do,
        raw_text=match.group(0),
    )
    return cleaned, suggestion