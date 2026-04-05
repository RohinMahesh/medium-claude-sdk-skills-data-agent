from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from medium_claude_sdk_skills_data_agent.app import app
from version import MAJOR, __version__


@pytest.mark.parametrize(
    "attr, expected",
    [
        ("title", "BigQuery Agent API"),
        ("version", __version__),
    ],
)
def test_app_attributes(attr, expected):
    assert getattr(app, attr) == expected


@pytest.mark.parametrize(
    "expected_path",
    [
        f"/api/v{MAJOR}/health",
        f"/api/v{MAJOR}/clean-up",
        f"/api/v{MAJOR}/conversation-history",
        f"/api/v{MAJOR}/chat",
    ],
)
def test_app_routes_registered(expected_path):
    route_paths = [route.path for route in app.routes]
    assert expected_path in route_paths


def test_app_is_fastapi_instance():
    assert isinstance(app, FastAPI)


@pytest.mark.asyncio
async def test_app_lifespan():
    from medium_claude_sdk_skills_data_agent.app import lifespan

    mock_fastapi_app = MagicMock()

    with (
        patch(
            "medium_claude_sdk_skills_data_agent.app.BigQueryAdapter"
        ) as mock_adapter_cls,
        patch(
            "medium_claude_sdk_skills_data_agent.app.AgentService"
        ) as mock_service_cls,
        patch(
            "medium_claude_sdk_skills_data_agent.app.get_schema",
            new=AsyncMock(return_value="mocked_schema"),
        ),
    ):
        mock_adapter_cls.return_value = MagicMock()
        mock_service_cls.return_value = MagicMock()

        async with lifespan(mock_fastapi_app):
            assert mock_fastapi_app.state.agent_service is mock_service_cls.return_value
            assert mock_fastapi_app.state.schema == "mocked_schema"
