"""Security regressions for gateway use of the local agy process provider."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


@pytest.mark.parametrize(
    "runtime",
    [
        {"provider": "agy"},
        {"provider": "antigravity"},
        {"provider": "antigravity-cli"},
        {"provider": "custom", "base_url": "agy://local"},
    ],
)
def test_gateway_policy_rejects_every_agy_route(runtime):
    from gateway.provider_policy import GatewayProviderPolicyError, enforce_gateway_provider_policy

    with pytest.raises(GatewayProviderPolicyError, match="auto-approve native tools"):
        enforce_gateway_provider_policy(runtime)


def test_gateway_policy_allows_non_agy_provider():
    from gateway.provider_policy import enforce_gateway_provider_policy

    runtime = {
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
    }

    assert enforce_gateway_provider_policy(runtime) is runtime


def test_gateway_runtime_resolution_rejects_configured_agy(monkeypatch):
    from gateway import run as gateway_run
    from gateway.provider_policy import GatewayProviderPolicyError

    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda *args, **kwargs: {
            "provider": "agy",
            "base_url": "agy://local",
            "command": "agy",
            "args": [],
        },
    )

    with pytest.raises(GatewayProviderPolicyError):
        gateway_run._resolve_runtime_agent_kwargs()


def test_gateway_fast_session_override_cannot_bypass_policy(monkeypatch):
    from gateway import run as gateway_run
    from gateway.provider_policy import GatewayProviderPolicyError

    runner = object.__new__(gateway_run.GatewayRunner)
    runner._session_model_overrides = {
        "session-1": {
            "model": "Gemini 3.5 Flash (Low)",
            "provider": "agy",
            # Exercise the early-return path used by credential-bearing overrides.
            "api_key": "test-only-nonsecret",
            "base_url": "agy://local",
        }
    }
    monkeypatch.setattr(gateway_run, "_load_topic_models", lambda: {})
    monkeypatch.setattr(gateway_run, "_resolve_gateway_model", lambda _cfg=None: "default-model")

    with pytest.raises(GatewayProviderPolicyError):
        runner._resolve_session_agent_runtime(session_key="session-1")


def test_gateway_turn_config_revalidates_runtime(monkeypatch):
    from gateway import run as gateway_run
    from gateway.provider_policy import GatewayProviderPolicyError

    runner = object.__new__(gateway_run.GatewayRunner)
    runner._service_tier = None

    with pytest.raises(GatewayProviderPolicyError):
        runner._resolve_turn_agent_config(
            "untrusted message",
            "Gemini 3.5 Flash (Low)",
            {"provider": "custom", "base_url": "agy://local"},
        )


def test_api_server_route_cannot_inject_agy_base_url(monkeypatch):
    from gateway.provider_policy import GatewayProviderPolicyError

    fake_agent = MagicMock(name="AIAgent")
    monkeypatch.setattr("run_agent.AIAgent", fake_agent)
    monkeypatch.setattr(
        "gateway.run._resolve_runtime_agent_kwargs",
        lambda: {
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_mode": "chat_completions",
        },
    )
    monkeypatch.setattr("gateway.run._resolve_gateway_model", lambda: "safe/model")
    monkeypatch.setattr("gateway.run._load_gateway_config", lambda: {})
    monkeypatch.setattr(
        "gateway.run.GatewayRunner._load_reasoning_config",
        staticmethod(lambda: {}),
    )
    monkeypatch.setattr(
        "gateway.run.GatewayRunner._load_fallback_model",
        staticmethod(lambda: None),
    )
    monkeypatch.setattr("gateway.run._current_max_iterations", lambda: 90)
    monkeypatch.setattr("hermes_cli.tools_config._get_platform_tools", lambda *_: set())

    adapter = APIServerAdapter(PlatformConfig(enabled=True))
    monkeypatch.setattr(adapter, "_ensure_session_db", lambda: None)

    with pytest.raises(GatewayProviderPolicyError):
        adapter._create_agent(
            session_id="api-session",
            route={"model": "unsafe/model", "base_url": "agy://local"},
        )

    fake_agent.assert_not_called()
