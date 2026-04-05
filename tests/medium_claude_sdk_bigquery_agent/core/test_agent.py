import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from medium_claude_sdk_skills_data_agent.core.agent import AgentService


@pytest.fixture
def mock_langfuse_client():
    mock_span = MagicMock()
    mock_span.id = "mock-span-id"
    mock_client = MagicMock()
    mock_client.create_trace_id.return_value = "mock-trace-id"
    mock_client.start_observation.return_value = mock_span
    return mock_client, mock_span


@pytest.fixture
def mock_agent_service_instance(mock_langfuse_client):
    mock_langfuse, _ = mock_langfuse_client
    mock_bq_port = MagicMock()
    mock_bq_tool = MagicMock()
    mock_mcp_server = MagicMock()

    env_patch = {"ANTHROPIC_VERTEX_PROJECT_ID": "test-project-1"}

    with (
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.create_bq_tool",
            return_value=mock_bq_tool,
        ),
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.create_sdk_mcp_server",
            return_value=mock_mcp_server,
        ),
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.get_client",
            return_value=mock_langfuse,
        ),
        patch.dict("os.environ", env_patch),
    ):
        service = AgentService(bq_port=mock_bq_port)
        return service


@pytest.mark.parametrize(
    "project_id_env",
    [
        "test-project-1",
        "test-project-2",
        None,
    ],
)
def test_agent_service_init(project_id_env):
    mock_bq_port = MagicMock()
    mock_bq_tool = MagicMock()
    mock_mcp_server = MagicMock()
    mock_langfuse = MagicMock()

    env_patch = (
        {"ANTHROPIC_VERTEX_PROJECT_ID": project_id_env} if project_id_env else {}
    )

    with (
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.create_bq_tool",
            return_value=mock_bq_tool,
        ) as mock_create_tool,
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.create_sdk_mcp_server",
            return_value=mock_mcp_server,
        ) as mock_create_server,
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.get_client",
            return_value=mock_langfuse,
        ) as mock_get_client,
        patch.dict("os.environ", env_patch),
    ):
        service = AgentService(bq_port=mock_bq_port)

    assert service.bq_port is mock_bq_port
    assert service._mcp_server is mock_mcp_server
    assert service.langfuse is mock_langfuse
    mock_create_tool.assert_called_once_with(bq_port=mock_bq_port)
    mock_create_server.assert_called_once()
    mock_get_client.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_id, question, schema, session_id, expected_result",
    [
        (
            "user-1",
            "What are total sales?",
            "schema_str",
            "session-1",
            "Total sales: $50,000",
        ),
        ("user-2", "Top products?", "schema_str", "session-2", "Top product: Widget A"),
        ("user-3", "Simple query", "", "session-3", "Answer"),
    ],
)
async def test_agent_service_run(
    mock_agent_service_instance,
    mock_langfuse_client,
    user_id,
    question,
    schema,
    session_id,
    expected_result,
):
    mock_langfuse, mock_run_span = mock_langfuse_client

    async def _message_gen():
        msg = MagicMock()
        msg.result = expected_result
        yield msg

    mock_client_instance = MagicMock()
    mock_client_instance.connect = AsyncMock()
    mock_client_instance.query = AsyncMock()
    mock_client_instance.disconnect = AsyncMock()
    mock_client_instance.receive_messages.return_value = _message_gen()
    mock_client_instance.get_context_usage = AsyncMock(
        return_value={
            "percentage": 7.0,
            "autoCompactThreshold": 167000,
            "isAutoCompactEnabled": True,
        }
    )

    with (
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.AgentService._ensure_compaction_settings"
        ),
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.get_session_messages",
            return_value=[],
        ),
        patch("medium_claude_sdk_skills_data_agent.core.agent.AgentDefinition"),
        patch("medium_claude_sdk_skills_data_agent.core.agent.ClaudeAgentOptions"),
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.ClaudeSDKClient",
            return_value=mock_client_instance,
        ),
    ):
        result, returned_session_id = await mock_agent_service_instance.run(
            question=question, schema=schema, user_id=user_id, session_id=session_id
        )

    expected_thread_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{user_id}:{session_id}"))
    assert result == expected_result
    assert returned_session_id == expected_thread_id
    mock_client_instance.connect.assert_called_once()
    mock_client_instance.query.assert_called_once_with(
        prompt=question, session_id=expected_thread_id
    )
    mock_client_instance.get_context_usage.assert_called_once()
    mock_client_instance.disconnect.assert_called_once()

    mock_langfuse.create_trace_id.assert_called_once_with(seed=expected_thread_id)
    mock_langfuse.start_observation.assert_called_once()
    mock_run_span.update.assert_called_once()
    mock_run_span.end.assert_called_once()
    mock_langfuse.flush.assert_called_once()


@pytest.mark.asyncio
async def test_agent_service_run_error(
    mock_agent_service_instance, mock_langfuse_client
):
    _, mock_run_span = mock_langfuse_client

    with (
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.AgentService._ensure_compaction_settings"
        ),
        patch(
            "medium_claude_sdk_skills_data_agent.core.agent.get_session_messages",
            side_effect=RuntimeError("session error"),
        ),
    ):
        result, returned_session_id = await mock_agent_service_instance.run(
            question="q", schema="s", user_id="u", session_id="sid"
        )

    assert result == ""
    assert returned_session_id == "sid"
    mock_run_span.update.assert_called_once_with(
        output={"error": "session error"}, level="ERROR"
    )
    mock_run_span.end.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["auto", "manual"])
async def test_pre_compact_hook(mock_agent_service_instance, trigger):
    hook_input = MagicMock()
    hook_input.trigger = trigger

    result = await mock_agent_service_instance._pre_compact_hook(
        hook_input=hook_input,
        _tool_use_id=None,
        _context={"signal": None},
    )

    assert result == {"continue_": True}


@pytest.mark.asyncio
async def test_pre_tool_hook(mock_agent_service_instance, mock_langfuse_client):
    mock_langfuse, mock_span = mock_langfuse_client

    # Set ContextVars so the hook can read them
    AgentService._ctx_trace_id.set("trace-123")
    AgentService._ctx_run_span_id.set("span-456")

    hook_input = {
        "tool_use_id": "tool-abc",
        "tool_name": "execute_query",
        "tool_input": {"query": "SELECT 1"},
    }

    result = await mock_agent_service_instance._pre_tool_hook(
        hook_input=hook_input,
        _tool_use_id=None,
        _context={"signal": None},
    )

    assert result == {"continue_": True}
    assert "tool-abc" in mock_agent_service_instance._active_tool_starts
    assert mock_agent_service_instance._active_tool_spans["tool-abc"] is mock_span
    mock_langfuse.start_observation.assert_called_once()
    call_kwargs = mock_langfuse.start_observation.call_args.kwargs
    assert call_kwargs["as_type"] == "tool"
    assert call_kwargs["name"] == "execute_query"
    assert call_kwargs["input"] == {"query": "SELECT 1"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hook_name, hook_input, seed_span, expected_output, expected_level",
    [
        (
            "_post_tool_hook",
            {"tool_use_id": "tool-abc", "tool_response": {"rows": [1, 2, 3]}},
            True,
            {"rows": [1, 2, 3]},
            None,
        ),
        (
            "_post_tool_failure_hook",
            {"tool_use_id": "tool-abc", "error": "BQ timeout"},
            True,
            {"error": "BQ timeout"},
            "ERROR",
        ),
        (
            "_post_tool_hook",
            {"tool_use_id": "unknown-id", "tool_response": "ok"},
            False,
            None,
            None,
        ),
        (
            "_post_tool_failure_hook",
            {"tool_use_id": "unknown-id", "error": "some error"},
            False,
            None,
            None,
        ),
    ],
)
async def test_post_tool_hook(
    mock_agent_service_instance,
    hook_name,
    hook_input,
    seed_span,
    expected_output,
    expected_level,
):
    mock_span = MagicMock()
    tool_use_id = hook_input["tool_use_id"]
    if seed_span:
        mock_agent_service_instance._active_tool_spans[tool_use_id] = mock_span
        mock_agent_service_instance._active_tool_starts[tool_use_id] = 0.0

    result = await getattr(mock_agent_service_instance, hook_name)(
        hook_input=hook_input,
        _tool_use_id=None,
        _context={"signal": None},
    )

    assert result == {"continue_": True}
    assert tool_use_id not in mock_agent_service_instance._active_tool_spans
    assert tool_use_id not in mock_agent_service_instance._active_tool_starts
    if seed_span:
        mock_span.update.assert_called_once()
        update_kwargs = mock_span.update.call_args.kwargs
        assert update_kwargs["output"] == expected_output
        assert "duration_ms" in update_kwargs["metadata"]
        if expected_level is not None:
            assert update_kwargs["level"] == expected_level
        mock_span.end.assert_called_once()
    else:
        mock_span.update.assert_not_called()
        mock_span.end.assert_not_called()


@pytest.mark.parametrize(
    "existing_content",
    [
        None,
        {},
        {"autoCompactEnabled": False},
        {"autoCompactEnabled": True},
    ],
)
def test_ensure_compaction_settings(tmp_path, existing_content):
    settings_dir = tmp_path / ".claude"
    settings_path = settings_dir / "settings.json"

    if existing_content is not None:
        settings_dir.mkdir()
        settings_path.write_text(json.dumps(existing_content))

    AgentService._ensure_compaction_settings(working_directory=str(tmp_path))

    assert settings_path.exists()
    written = json.loads(settings_path.read_text())
    assert written.get("autoCompactEnabled") is True
