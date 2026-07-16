from types import SimpleNamespace

import pytest

from hermes_cli import auth
from hermes_cli.auth import AuthError
from hermes_cli.runtime_provider import (
    provider_requires_fail_closed,
    resolve_runtime_provider,
)
from hermes_cli.inventory import ConfigContext, build_models_payload
from hermes_cli.model_switch import list_authenticated_providers, list_picker_providers
from hermes_cli.models import (
    CANONICAL_PROVIDERS,
    list_available_providers,
    normalize_provider,
    parse_model_input,
)
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


@pytest.mark.parametrize("alias", ["antigravity", "antigravity-cli"])
def test_agy_model_switch_aliases_follow_provider_profile(alias):
    assert normalize_provider(alias) == "agy"
    assert parse_model_input(
        f"{alias}:Gemini 3.5 Flash (Low)", "openrouter"
    ) == ("agy", "Gemini 3.5 Flash (Low)")
    agy = next(row for row in list_available_providers() if row["id"] == "agy")
    assert alias in agy["aliases"]


def test_agy_external_process_inventory_populates_shared_tui_desktop_payload(
    monkeypatch,
):
    monkeypatch.setattr(auth.shutil, "which", lambda command: "/usr/local/bin/agy")
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr("hermes_cli.models.get_curated_nous_model_ids", lambda: [])
    monkeypatch.setattr("hermes_cli.models.fetch_ollama_cloud_models", lambda: [])
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"agy": {"command": "agy"}},
    )

    providers = list_authenticated_providers(current_provider="agy")
    picker = list_picker_providers(current_provider="agy")
    payload = build_models_payload(
        ConfigContext("agy", "Gemini 3.5 Flash (Low)", "agy://local", {}, []),
        explicit_only=True,
        include_unconfigured=True,
        picker_hints=True,
        canonical_order=True,
    )

    for rows in (providers, picker, payload["providers"]):
        agy = next(row for row in rows if row["slug"] == "agy")
        assert agy["models"]
        assert "Gemini 3.5 Flash (Low)" in agy["models"]
    payload_agy = next(row for row in payload["providers"] if row["slug"] == "agy")
    assert payload_agy["authenticated"] is True
    assert payload_agy["total_models"] == len(payload_agy["models"])


def test_agy_is_populated_in_tui_and_desktop_model_options(monkeypatch):
    from hermes_cli import web_server
    from tui_gateway import server

    monkeypatch.setattr(auth.shutil, "which", lambda command: "/usr/local/bin/agy")
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr("agent.models_dev.get_model_capabilities", lambda *args: None)
    monkeypatch.setattr("hermes_cli.models.get_curated_nous_model_ids", lambda: [])
    monkeypatch.setattr("hermes_cli.models.fetch_ollama_cloud_models", lambda: [])
    monkeypatch.setattr("hermes_cli.models.get_pricing_for_provider", lambda slug: {})
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {"agy": {"command": "agy"}},
    )

    desktop = web_server.get_model_options(explicit_only=True)
    tui = server._methods["model.options"](
        42, {"session_id": "", "include_unconfigured": True}
    )["result"]

    for payload in (desktop, tui):
        agy = next(row for row in payload["providers"] if row["slug"] == "agy")
        assert agy["configured"] is True
        assert agy["authenticated"] is True
        assert "Gemini 3.5 Flash (Low)" in agy["models"]


@pytest.mark.parametrize("alias", ["antigravity", "antigravity-cli"])
def test_agy_alias_persists_canonical_provider(alias, monkeypatch):
    from tui_gateway import server

    provider, model = parse_model_input(
        f"{alias}:Gemini 3.5 Flash (Low)", "openrouter"
    )
    saved = {}
    monkeypatch.setattr(
        "cli.save_config_value",
        lambda key, value: saved.__setitem__(key, value) or True,
    )

    server._persist_model_switch(
        SimpleNamespace(new_model=model, target_provider=provider, base_url="agy://local")
    )

    assert saved["model.default"] == "Gemini 3.5 Flash (Low)"
    assert saved["model.provider"] == "agy"


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
    assert status["auth_verified"] is False
    assert status["status_basis"] == "process_available"
