from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk import SdkMcpTool

from medium_claude_sdk_skills_data_agent.adapters.bigquery_adapter import (
    BigQueryAdapter,
    create_bq_tool,
)
from medium_claude_sdk_skills_data_agent.core.ports import BigQueryPort
from medium_claude_sdk_skills_data_agent.utils.constants import TOOL_NAME


@pytest.fixture
def mock_bigquery_adapter():
    with patch(
        "medium_claude_sdk_skills_data_agent.adapters.bigquery_adapter.bigquery.Client"
    ):
        adapter = BigQueryAdapter(project_id="test-project", location="us-central1")
        return adapter


@pytest.mark.parametrize(
    "project_id, location",
    [
        ("test-project", "us-central1"),
        ("another-project", "us-east1"),
        (None, None),
    ],
)
def test_bigquery_adapter_init(project_id, location):
    with patch(
        "medium_claude_sdk_skills_data_agent.adapters.bigquery_adapter.bigquery.Client"
    ) as mock_client_cls:
        adapter = BigQueryAdapter(project_id=project_id, location=location)

    assert adapter.project_id == project_id
    assert adapter.location == location
    mock_client_cls.assert_called_once_with(project=project_id, location=location)


@pytest.mark.parametrize(
    "sql, rows, expected",
    [
        (
            "SELECT * FROM table",
            [{"id": 1, "name": "Alice"}],
            [{"id": 1, "name": "Alice"}],
        ),
        (
            "SELECT COUNT(*) FROM table",
            [{"count": 42}],
            [{"count": 42}],
        ),
        (
            "SELECT id FROM table WHERE id = 99",
            [],
            [],
        ),
    ],
)
def test_execute_query(mock_bigquery_adapter, sql, rows, expected):
    mock_job = MagicMock()
    mock_job.job_id = "job-abc"
    mock_job.location = "us-central1"
    mock_job.result.return_value = rows

    mock_bq_client = MagicMock()
    mock_bq_client.query.return_value = mock_job

    with patch(
        "medium_claude_sdk_skills_data_agent.adapters.bigquery_adapter.bigquery_poll"
    ), patch.object(
        BigQueryAdapter,
        "execute_query",
        return_value=expected,
    ) as mock_exec:
        result = mock_bigquery_adapter.execute_query(sql)

    mock_exec.assert_called_once_with(sql)
    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql, sync_result",
    [
        ("SELECT * FROM t", [{"col": "val"}]),
        ("SELECT COUNT(*) FROM t", [{"n": 5}]),
        ("SELECT id FROM t WHERE id = 1", []),
    ],
)
async def test_execute_query_async(mock_bigquery_adapter, sql, sync_result):
    with patch.object(
        mock_bigquery_adapter, "execute_query", return_value=sync_result
    ) as mock_sync:
        result = await mock_bigquery_adapter.execute_query_async({"sql": sql})

    mock_sync.assert_called_once_with(sql)
    assert result == {"content": [{"type": "text", "text": str(sync_result)}]}


@pytest.mark.parametrize(
    "bq_port_type",
    [
        "mock_port",
        "concrete_port",
    ],
)
def test_create_bq_tool(bq_port_type):
    if bq_port_type == "mock_port":
        bq_port = MagicMock(spec=BigQueryPort)
        bq_port.execute_query_async = AsyncMock()
    else:

        class ConcreteBQPort(BigQueryPort):
            def execute_query(self, _):
                return []

            async def execute_query_async(self, _):
                return []

        bq_port = ConcreteBQPort()

    tool_fn = create_bq_tool(bq_port)

    assert isinstance(tool_fn, SdkMcpTool)
    assert tool_fn.name == TOOL_NAME
