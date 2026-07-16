from unittest.mock import MagicMock, patch

from agent.auxiliary_client import resolve_provider_client
from run_agent import AIAgent


def _agent(**kwargs):
    return AIAgent(
        api_key="agy-external-process",
        base_url="agy://local",
        model="Gemini 3.5 Flash (Low)",
        provider="agy",
        acp_command="/usr/local/bin/agy",
        acp_args=[],
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
        **kwargs,
    )


def test_aiagent_uses_agy_cli_client_instead_of_openai_http():
    with (
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("agent.agy_cli_client.AgyCLIClient") as mock_agy_client,
        patch("run_agent.OpenAI") as mock_openai,
    ):
        process_client = MagicMock()
        mock_agy_client.return_value = process_client
        agent = _agent()

    assert agent.client is process_client
    mock_openai.assert_not_called()
    assert mock_agy_client.call_args.kwargs["command"] == "/usr/local/bin/agy"
    assert mock_agy_client.call_args.kwargs["args"] == []


def test_agy_primary_filters_direct_gemini_api_fallbacks():
    with (
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("agent.agy_cli_client.AgyCLIClient", return_value=MagicMock()),
    ):
        agent = _agent(
            fallback_model=[
                {"provider": "gemini", "model": "gemini-3-flash"},
                {
                    "provider": "custom",
                    "model": "gemini-3-flash",
                    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                },
                {"provider": "openai-codex", "model": "gpt-5.4"},
            ]
        )

    assert agent._fallback_chain == []
    assert getattr(agent, "_api_max_retries") == 1


def test_auxiliary_client_uses_agy_process_route_without_http():
    runtime = {
        "provider": "agy",
        "api_mode": "chat_completions",
        "base_url": "agy://local",
        "api_key": "agy-external-process",
        "command": "/usr/local/bin/agy",
        "args": [],
        "source": "process",
        "requested_provider": "agy",
    }
    with (
        patch(
            "hermes_cli.auth.resolve_external_process_provider_credentials",
            return_value=runtime,
        ),
        patch("agent.agy_cli_client.AgyCLIClient") as mock_agy,
    ):
        process_client = MagicMock()
        mock_agy.return_value = process_client
        client, model = resolve_provider_client(
            "agy", model="Gemini 3.5 Flash (Low)"
        )

    assert client is process_client
    assert model == "Gemini 3.5 Flash (Low)"
    assert mock_agy.call_args.kwargs["command"] == "/usr/local/bin/agy"
