import pytest

from hermes_cli import auth
from hermes_cli.auth import AuthError
from hermes_cli.runtime_provider import (
    provider_requires_fail_closed,
    resolve_runtime_provider,
)
from hermes_cli.models import CANONICAL_PROVIDERS
from hermes_cli.provider_catalog import provider_catalog_by_slug
from providers import get_provider_profile


def test_agy_provider_is_keyless_external_process():
    profile = get_provider_profile("agy")

    assert profile is not None
    assert profile.auth_type == "external_process"
    assert profile.base_url == "agy://local"
    assert profile.env_vars == ()
    assert profile.supports_health_check is False
    assert profile.fail_closed is True
    assert "antigravity" in profile.aliases


def test_agy_is_available_to_cli_tui_and_desktop_provider_pickers():
    assert "agy" in {entry.slug for entry in CANONICAL_PROVIDERS}
    descriptor = provider_catalog_by_slug()["agy"]
    assert descriptor.auth_type == "external_process"
    assert descriptor.tab == "accounts"
    assert descriptor.api_key_env_vars == ()


def test_agy_provider_failure_is_fail_closed_for_name_alias_and_auth_error():
    assert provider_requires_fail_closed("agy") is True
    assert provider_requires_fail_closed("antigravity") is True
    assert provider_requires_fail_closed(
        "auto", error=AuthError("missing", provider="agy")
    ) is True
    assert provider_requires_fail_closed("gemini") is False
    assert provider_requires_fail_closed(
        "custom", base_url="agy://local"
    ) is True


def test_agy_runtime_resolves_local_cli_without_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(auth.shutil, "which", lambda command: "/usr/local/bin/agy")
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"agy": {"command": "agy"}},
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "must-not-be-read")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-read")

    resolved = resolve_runtime_provider(requested="agy")

    assert resolved["provider"] == "agy"
    assert resolved["base_url"] == "agy://local"
    assert resolved["api_key"] == "agy-external-process"
    assert resolved["command"] == "/usr/local/bin/agy"
    assert resolved["args"] == []
    assert resolved["source"] == "process"
    assert "googleapis.com" not in resolved["base_url"]


def test_agy_missing_cli_raises_fail_closed_auth_error(monkeypatch):
    monkeypatch.setattr(auth.shutil, "which", lambda command: None)
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"agy": {"command": "/missing/agy"}},
    )

    with pytest.raises(AuthError) as exc_info:
        resolve_runtime_provider(requested="agy")

    assert exc_info.value.provider == "agy"
    assert exc_info.value.code == "missing_agy_cli"
    assert provider_requires_fail_closed(error=exc_info.value) is True


@pytest.mark.parametrize("alias", ["antigravity", "antigravity-cli"])
def test_agy_alias_status_uses_canonical_external_process(alias, monkeypatch):
    monkeypatch.setattr(auth.shutil, "which", lambda command: "/usr/local/bin/agy")
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"agy": {"command": "agy"}},
    )

    status = auth.get_external_process_provider_status(alias)

    assert status["configured"] is True
    assert status["provider"] == "agy"
    assert status["command"] == "agy"
    assert status["args"] == []
