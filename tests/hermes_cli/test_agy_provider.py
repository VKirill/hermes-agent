from hermes_cli import auth
from hermes_cli.auth import AuthError
from hermes_cli.runtime_provider import (
    provider_requires_fail_closed,
    resolve_runtime_provider,
)
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


def test_agy_provider_failure_is_fail_closed_for_name_alias_and_auth_error():
    assert provider_requires_fail_closed("agy") is True
    assert provider_requires_fail_closed("antigravity") is True
    assert provider_requires_fail_closed(
        "auto", error=AuthError("missing", provider="agy")
    ) is True
    assert provider_requires_fail_closed("gemini") is False


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
