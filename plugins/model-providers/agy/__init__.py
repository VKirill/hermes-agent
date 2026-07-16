"""Antigravity CLI external-process provider.

This profile is intentionally keyless: authentication stays inside the local
``agy`` CLI and its OS-managed session.
"""

from providers import register_provider
from providers.base import ProviderProfile

PROFILE = ProviderProfile(
    name="agy",
    display_name="Antigravity CLI (managed local process)",
    description=(
        "Uses the local agy CLI OAuth transport to remote Google Cloud Code Assist; "
        "Hermes does not use GOOGLE_API_KEY or GEMINI_API_KEY. Disabled in gateway "
        "sessions because agy headless mode can auto-approve native tools."
    ),
    aliases=("antigravity", "antigravity-cli"),
    env_vars=(),
    base_url="agy://local",
    auth_type="external_process",
    api_mode="chat_completions",
    supports_health_check=False,
    fail_closed=True,
    fallback_models=(
        "Gemini 3.5 Flash (Low)",
        "Gemini 3.5 Flash (Medium)",
        "Gemini 3.5 Flash (High)",
        "Gemini 3.1 Pro (Low)",
        "Gemini 3.1 Pro (High)",
    ),
)

register_provider(PROFILE)
