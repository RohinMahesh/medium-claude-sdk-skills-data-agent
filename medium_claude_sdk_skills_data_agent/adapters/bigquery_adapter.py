import asyncio
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import tool
from google.cloud import bigquery

from medium_claude_sdk_skills_data_agent.core.ports import BigQueryPort
from medium_claude_sdk_skills_data_agent.utils.constants import (
    TOOL_DESCRIPTION,
    TOOL_NAME,
)
from medium_claude_sdk_skills_data_agent.utils.helpers import (
    bigquery_poll,
    create_logger,
)


def create_bq_tool(bq_port: BigQueryPort):
    """
    Creates a claude_agent_sdk tool bound to the given BigQueryPort

    :param bq_port: the BigQuery port implementation to bind
    :returns tool-decorated coroutine ready for MCP server registration
    """
    return tool(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        input_schema={"sql": str},
    )(bq_port.execute_query_async)


@dataclass
class BigQueryAdapter(BigQueryPort):
    """
    Outbound adapter that executes read-only SQL queries against Google BigQuery

    :param project_id: the GCP project ID for the BigQuery table
    :param location: the GCP region where the BigQuery dataset is located
    """

    project_id: str | None = field(default=None)
    location: str | None = field(default=None)

    def __post_init__(self):
        self.logger = create_logger(name="BigQueryAdapter")
        self.client = bigquery.Client(project=self.project_id, location=self.location)

    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        """
        Executes a SQL query synchronously against BigQuery

        :param sql: the SQL query to execute
        :returns list of result rows as dictionaries
        """
        # Submit job with query to execute
        self.logger.info(f"Executing SQL query: {sql}")
        submitted_job = self.client.query(query=sql, location=self.location)
        _jid = submitted_job.job_id
        _jloc = submitted_job.location

        # Poll for completion
        bigquery_poll(client=self.client, jid=_jid, jloc=_jloc, timeout=20, interval=1)

        # Return data
        self.logger.info("Polling complete, formatting results")
        rows = submitted_job.result()
        return [dict(row) for row in rows]

    async def execute_query_async(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Executes a SQL query asynchronously in a thread pool

        :param args: dictionary containing key 'sql' with the query string
        :returns an MCP-formatted content dict with query results as text
        """
        rows = await asyncio.to_thread(self.execute_query, args["sql"])
        return {"content": [{"type": "text", "text": str(rows)}]}
