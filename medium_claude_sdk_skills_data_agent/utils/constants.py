DEFAULT_MODEL = "claude-sonnet-4-6"
MCP_SERVER_NAME = "bigquery_api"
MCP_SERVER_VERSION = "0.1.0"
AGENT_NAME = "bigquery-agent"
AGENT_DESCRIPTION = (
    "Agent with access to BigQuery tables for executing queries and "
    "retrieving schema information."
)
TOOL_NAME = "execute_bigquery_query"
TOOL_DESCRIPTION = (
    "Executes a SQL query against BigQuery and returns the results. "
    "Use this tool to retrieve schema information using a generated query."
)
DEFAULT_LLM_ENV_VAR = "LLM"
BQ_CLIENT_ENV_VAR = "bq_client"
FIRESTORE_MESSAGES_FIELD = "messages"
CLAUDE_SETTINGS_JSON = {"autoCompactEnabled": True}
