import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from medium_claude_sdk_skills_data_agent.api.router import router


def make_client(
    agent_run_return=("result", "session-123"),
    schema="test_schema",
    agent_run_exception=None,
):
    """Build a TestClient with a fully mocked app state."""
    app = FastAPI()
    app.include_router(router=router, prefix="/api/v0")
    mock_service = MagicMock()
    if agent_run_exception:
        mock_service.run = AsyncMock(side_effect=agent_run_exception)
    else:
        mock_service.run = AsyncMock(return_value=agent_run_return)
    app.state.agent_service = mock_service
    app.state.schema = schema
    app.state.plugin_sync = MagicMock()
    return TestClient(app)


@pytest.mark.parametrize(
    "expected_status, expected_body",
    [
        (200, {"status": "healthy"}),
    ],
)
def test_health_check(expected_status, expected_body):
    client = make_client()
    response = client.get("/api/v0/health")

    assert response.status_code == expected_status
    assert response.json() == expected_body


@pytest.mark.parametrize(
    "request_body, run_return, exception, expected_status",
    [
        (
            {"question": "What are total sales?"},
            ("Total sales: $50k", "session-abc"),
            None,
            200,
        ),
        (
            {"question": "Top states?", "session_id": "existing-session"},
            ("NY leads", "existing-session"),
            None,
            200,
        ),
        ({"question": ""}, None, None, 422),
        ({}, None, None, 422),
        (
            {"question": "What are sales?"},
            None,
            RuntimeError("BigQuery connection failed"),
            500,
        ),
        (
            {"question": "What are sales?"},
            None,
            RuntimeError("Agent SDK error"),
            500,
        ),
    ],
)
def test_chat(request_body, run_return, exception, expected_status):
    client = make_client(agent_run_return=run_return, agent_run_exception=exception)
    response = client.post("/api/v0/chat", json=request_body)

    assert response.status_code == expected_status
    if run_return is not None:
        body = response.json()
        assert body["result"] == run_return[0]
        assert body["session_id"] == run_return[1]
    if exception is not None:
        assert str(exception) in response.json()["detail"]


@pytest.mark.parametrize(
    "user_id, session_id, messages_return, expected_status, expected_body",
    [
        (
            "test-user",
            "missing-session",
            [],
            404,
            {
                "detail": "No conversation found for user_id: test-user, session_id: missing-session"
            },
        ),
        (
            "test-user",
            "valid-session",
            [
                MagicMock(
                    type="human",
                    uuid="uuid-1",
                    session_id="valid-session",
                    message={"role": "user", "content": "hello"},
                )
            ],
            200,
            {
                "session_id": str(
                    uuid.uuid5(uuid.NAMESPACE_DNS, "test-user:valid-session")
                ),
                "messages": [
                    {
                        "type": "human",
                        "uuid": "uuid-1",
                        "session_id": "valid-session",
                        "message": {"role": "user", "content": "hello"},
                    }
                ],
            },
        ),
    ],
)
def test_conversation_history(
    user_id, session_id, messages_return, expected_status, expected_body
):
    with patch(
        "medium_claude_sdk_skills_data_agent.api.router.get_session_messages",
        return_value=messages_return,
    ):
        client = make_client()
        response = client.get(
            "/api/v0/conversation-history",
            params={"session_id": session_id, "user_id": user_id},
        )

    assert response.status_code == expected_status
    assert response.json() == expected_body


@pytest.mark.parametrize(
    "project_dir_exists, expected_status, expected_status_value",
    [
        (False, 200, "nothing to clean"),
        (True, 200, "cleaned"),
    ],
)
def test_clean_up(project_dir_exists, expected_status, expected_status_value):
    mock_project_dir = MagicMock()
    mock_project_dir.exists.return_value = project_dir_exists

    with (
        patch(
            "medium_claude_sdk_skills_data_agent.api.router._canonicalize_path",
            return_value="/fake/path",
        ),
        patch(
            "medium_claude_sdk_skills_data_agent.api.router._find_project_dir",
            return_value=mock_project_dir if project_dir_exists else None,
        ),
        patch("medium_claude_sdk_skills_data_agent.api.router.shutil.rmtree"),
    ):
        client = make_client()
        response = client.delete("/api/v0/clean-up")

    assert response.status_code == expected_status
    assert response.json()["status"] == expected_status_value
