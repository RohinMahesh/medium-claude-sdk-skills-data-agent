import itertools
import logging
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import InternalServerError

from medium_claude_sdk_skills_data_agent.utils.helpers import (
    bigquery_poll,
    create_logger,
    get_schema,
)


@pytest.mark.parametrize(
    "name, level",
    [
        ("agent_logger", logging.INFO),
        ("debug_logger", logging.DEBUG),
        ("warning_logger", logging.WARNING),
    ],
)
def test_create_logger(name, level):
    logger = create_logger(name=name, level=level)

    assert logger.name == name
    assert logger.level == level
    assert not logger.propagate
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "project_id, dataset_id, table_id, fields",
    [
        (
            "proj-1",
            "dataset_1",
            "table_1",
            [
                ("row_id", "INTEGER", "REQUIRED", "Primary key"),
                ("name", "STRING", "NULLABLE", "Name field"),
            ],
        ),
        (
            "proj-2",
            "dataset_2",
            "table_2",
            [
                ("amount", "FLOAT", "REQUIRED", "Amount"),
            ],
        ),
    ],
)
async def test_get_schema(project_id, dataset_id, table_id, fields):
    mock_schema = []
    for col_name, ftype, mode, desc in fields:
        mock_field = MagicMock()
        mock_field.name = col_name
        mock_field.field_type = ftype
        mock_field.mode = mode
        mock_field.description = desc
        mock_schema.append(mock_field)

    mock_table = MagicMock()
    mock_table.schema = mock_schema
    mock_client = MagicMock()
    mock_client.get_table.return_value = mock_table

    with patch(
        "medium_claude_sdk_skills_data_agent.utils.helpers.bigquery.Client",
        return_value=mock_client,
    ):
        result = await get_schema(
            project_id=project_id, dataset_id=dataset_id, table_id=table_id
        )

    assert isinstance(result, str)
    for col_name, _, _, _ in fields:
        assert col_name in result
    mock_client.get_table.assert_called_once_with(
        f"{project_id}.{dataset_id}.{table_id}"
    )


@pytest.mark.parametrize(
    "side_effects, timeout, interval, raises",
    [
        (itertools.repeat(MagicMock(done=lambda: False)), 0, 0, True),
        ([MagicMock(done=lambda: True)], 1, 0, False),
        (
            [
                InternalServerError("mock-internal-server-error"),
                MagicMock(done=lambda: True),
            ],
            1,
            0,
            False,
        ),
    ],
)
def test_bigquery_poll(side_effects, timeout, interval, raises):
    dummy_client = MagicMock()
    dummy_client.get_job.side_effect = side_effects

    if not raises:
        bigquery_poll(
            client=dummy_client,
            jid="dummy-job",
            jloc="dummy-loc",
            timeout=timeout,
            interval=interval,
        )
    else:
        with pytest.raises(TimeoutError):
            bigquery_poll(
                client=dummy_client,
                jid="dummy-job",
                jloc="dummy-loc",
                timeout=timeout,
                interval=interval,
            )
