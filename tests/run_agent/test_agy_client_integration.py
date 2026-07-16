import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.auxiliary_client import resolve_provider_client
from agent.agy_cli_client import AgyCLIClient
from agent.chat_completion_helpers import try_activate_fallback
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


def test_custom_agy_url_applies_process_route_security_policy():
    with (
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("agent.agy_cli_client.AgyCLIClient", return_value=MagicMock()),
    ):
        agent = AIAgent(
            api_key="agy-external-process",
            base_url="agy://local",
            model="Gemini 3.5 Flash (Low)",
            provider="custom",
            acp_command="/usr/local/bin/agy",
            acp_args=[],
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            fallback_model=[  # type: ignore[arg-type]
                {"provider": "gemini", "model": "gemini-3-flash"}
            ],
        )

    assert getattr(agent, "_fallback_chain") == []
    assert getattr(agent, "_api_max_retries") == 1


def test_custom_agy_url_refuses_runtime_fallback_activation():
    agent = SimpleNamespace(
        provider="custom",
        base_url="agy://local",
        _fallback_chain=[{"provider": "gemini", "model": "gemini-3-flash"}],
    )

    assert try_activate_fallback(agent) is False
    assert agent.provider == "custom"
    assert agent._fallback_chain == [
        {"provider": "gemini", "model": "gemini-3-flash"}
    ]


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


def test_auxiliary_client_exposes_async_agy_adapter(monkeypatch, tmp_path):
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
    expected = SimpleNamespace(choices=[])
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profile"))
    monkeypatch.setattr(
        AgyCLIClient,
        "_create_chat_completion",
        lambda self, **kwargs: expected,
    )
    with patch(
        "hermes_cli.auth.resolve_external_process_provider_credentials",
        return_value=runtime,
    ):
        client, model = resolve_provider_client(
            "agy", model="Gemini 3.5 Flash (Low)", async_mode=True
        )

    response = asyncio.run(
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "async"}],
        )
    )

    assert response is expected


def test_agy_tool_call_reaches_hermes_tool_loop(monkeypatch, tmp_path):
    def fake_agy_run(argv, **kwargs):
        prompt_ref = argv[argv.index("-p") + 1]
        assert prompt_ref.startswith("@")
        with open(prompt_ref[1:], encoding="utf-8") as handle:
            prompt = handle.read()
        if "TOOL-OK" in prompt:
            stdout = "DONE\n"
        else:
            stdout = '<tool_call>{"id":"agy-loop-1","type":"function","function":{"name":"probe_tool","arguments":"{\\"value\\":\\"ping\\"}"}}</tool_call>\n'
        return SimpleNamespace(
            returncode=0,
            stdout=stdout,
            stderr="",
            stdout_exceeded=False,
            stderr_exceeded=False,
        )

    monkeypatch.setattr("agent.agy_cli_client._run_bounded_process", fake_agy_run)
    monkeypatch.setattr(
        "agent.agy_cli_client.load_config",
        lambda: {
            "agy": {
                "state_dir": str(tmp_path / "state"),
                "timeout_seconds": 5,
                "queue_timeout_seconds": 5,
                "retry_budget": 0,
                "dedupe_ttl_seconds": 0,
                "sandbox": True,
                "mode": "plan",
            }
        },
    )
    tool_schema = {
        "type": "function",
        "function": {
            "name": "probe_tool",
            "description": "Return a probe result.",
            "parameters": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        },
    }

    with (
        patch("run_agent.get_tool_definitions", return_value=[tool_schema]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.handle_function_call", return_value="TOOL-OK") as execute,
    ):
        agent = AIAgent(
            api_key="agy-external-process",
            base_url="agy://local",
            model="Gemini 3.5 Flash (Low)",
            provider="agy",
            acp_command="agy",
            acp_args=[],
            max_iterations=3,
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )
        result = agent.run_conversation("Use the probe tool, then finish.")

    assert result["completed"] is True
    assert result["final_response"] == "DONE"
    execute.assert_called_once()
    assert execute.call_args.args[0] == "probe_tool"
