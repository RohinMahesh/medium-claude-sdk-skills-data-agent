# Claude Agent SDK Skills Data Agent
![Build Status](https://github.com/RohinMahesh/medium-claude-sdk-skills-data-agent/actions/workflows/ci.yaml/badge.svg)

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Key Features](#key-features)
- [Setup](#setup)
- [Running the API](#running-the-api)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Code Quality](#code-quality)

---

## Overview

This project uses the Claude Agent SDK to build a skills-based BigQuery data agent with persistent session state, context management, and full observability via Langfuse:

- **Claude Agent SDK** — orchestrates a Claude model (`claude-sonnet-4-6`) with tool-calling, skills, and SDK lifecycle hooks
- **Skills & Plugins** — agent capabilities are packaged as plugins and auto-synced to the `.claude/` directory at startup
- **Model Context Protocol (MCP)** — exposes BigQuery execution as a tool the agent can invoke
- **Google BigQuery** — executes generated SQL and returns results
- **Google Firestore** — persists session checkpoint files so conversation state survives infrastructure scale-to-zero events
- **Context Management** — automatic context compaction is enabled via `.claude/settings.json`; the agent monitors usage and logs compaction events via a `PreCompact` hook
- **Langfuse Observability** — traces every agent run as a top-level span; individual tool calls are tracked as child spans with input, output, and duration via `PreToolUse` / `PostToolUse` hooks
- **FastAPI** — serves the agent as a REST API with session management and conversation history

The agent follows a structured prompting strategy defined in the `queries` skill:
1. Determines if the question requires a database lookup
2. Generates SQL from a dynamically injected table schema
3. Executes the SQL via the MCP BigQuery tool
4. Returns a user-friendly natural language answer

---

## Architecture

The project follows **Hexagonal Architecture (Ports & Adapters)** to cleanly separate domain logic from infrastructure:

```
┌────────────────────────────────────────────────────────────┐
│                         HTTP Layer                         │
│              FastAPI app.py + api/router.py                │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│                       Domain Layer                         │
│            core/agent.py (AgentService)                    │
│            core/ports.py (BigQueryPort, AgentServicePort,  │
│                           PersistencePort, PluginSyncPort) │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│                    Infrastructure Layer                    │
│      adapters/bigquery_adapter.py  (BigQueryAdapter)       │
│      adapters/firestore_adapter.py (FirestoreSessionStore) │
│      adapters/plugin_adapter.py    (PluginSync)            │
└────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
medium-claude-sdk-skills-data-agent/
├── medium_claude_sdk_skills_data_agent/
│   ├── app.py                       # FastAPI app + lifespan startup (plugin sync, adapters)
│   ├── core/
│   │   ├── agent.py                 # AgentService — Claude SDK orchestration, hooks, Langfuse
│   │   └── ports.py                 # Abstract interfaces (BigQueryPort, AgentServicePort,
│   │                                #   PersistencePort, PluginSyncPort)
│   ├── adapters/
│   │   ├── bigquery_adapter.py      # Google BigQuery adapter + MCP tool definition
│   │   ├── firestore_adapter.py     # Firestore session persistence adapter
│   │   └── plugin_adapter.py        # Plugin-to-.claude/ directory sync adapter
│   ├── api/
│   │   └── router.py                # API endpoint definitions
│   ├── plugins/
│   │   └── data-agent/              # Plugin package (auto-discovered at startup)
│   │       ├── .claude-plugin/
│   │       │   └── plugin.json      # Plugin manifest
│   │       ├── skills/
│   │       │   └── queries/
│   │       │       └── SKILL.md     # BigQuery SQL agent skill definition
│   │       └── commands/
│   │           ├── construct-query.md
│   │           └── execute-query.md
│   └── utils/
│       ├── constants.py             # App-wide constants (model, MCP server, Firestore, settings)
│       ├── file_paths.py            # Dataset/table/plugin/checkpoint path defaults
│       ├── helpers.py               # Logging, schema fetching, job polling
│       ├── objects.py               # Pydantic request/response models
│       └── prompts.py               # Claude system prompt template
├── tests/
│   └── medium_claude_sdk_bigquery_agent/
│       ├── adapters/
│       │   └── test_bigquery_adapter.py
│       ├── api/
│       │   └── test_router.py
│       ├── core/
│       │   ├── test_agent.py
│       │   └── test_ports.py
│       ├── utils/
│       │   └── test_helpers.py
│       └── test_app.py
├── .env.example                     # Environment variable template
├── .github/workflows/ci.yaml        # GitHub Actions CI pipeline
├── .pre-commit-config.yaml          # isort, black, ruff hooks
├── Makefile                         # Developer convenience commands
├── pyproject.toml                   # Ruff linter configuration
├── requirements.txt                 # Python dependencies
└── .python-version                  # Pinned Python version (3.12.13)
```

---

## Key Features

### Skills & Plugins

Agent capabilities are packaged as plugins under `plugins/`. At startup, `PluginSync` discovers all plugins (identified by a `.claude-plugin/plugin.json` manifest) and copies their `skills/` and `commands/` into the `.claude/` directory. The agent is initialized with the resulting skill names so they are active during each run.

The `queries` skill (`plugins/data-agent/skills/queries/SKILL.md`) defines the BigQuery SQL agent behavior, including instructions, SQL examples, and guardrails against data fabrication.

### Session Persistence (Firestore)

`FirestoreSessionStore` persists Claude Agent SDK checkpoint files (JSONL session state) in Firestore under the path `<user_id>/<thread_id>`. Before each run the adapter restores the checkpoint to disk; after a successful run it saves the latest state back. This ensures conversation history survives container restarts and scale-to-zero events.

Documents are organized as:
```
collection: <user_id>
document:   <thread_id>          # deterministic UUID5(user_id:session_id)
field:      messages             # list[dict] — one entry per JSONL line
```

### Context Management

Auto-compaction is enabled by writing `{"autoCompactEnabled": true}` to `.claude/settings.json` at the start of each run. The agent registers a `PreCompact` hook to log when compaction is triggered, and context usage (percentage, threshold, auto-compact status) is logged and attached to the Langfuse trace after each run.

### Observability (Langfuse)

Every agent run is instrumented with Langfuse:

| Hook | What is traced |
|---|---|
| `run` (span) | Full request: input question, output answer, user/session metadata, context usage % |
| `PreToolUse` | Tool call start: tool name + input, recorded as a child span |
| `PostToolUse` | Tool call success: output + wall-clock duration (ms) |
| `PostToolUseFailure` | Tool call error: error message + duration, logged at `ERROR` level |

Trace IDs are derived deterministically from `thread_id` so that all turns of a session map to the same Langfuse trace. Context variables (`ContextVar`) keep trace/span IDs request-scoped in async code.

---

## Setup

### Prerequisites

- Python 3.12.13 (managed via `conda` or `.python-version`)
- A Google Cloud project with BigQuery and Firestore enabled
- GCP credentials with BigQuery read and Firestore read/write permissions
- An Anthropic API key (via Vertex AI or direct)
- A Langfuse account (cloud or self-hosted) with a project API key

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd medium-claude-sdk-skills-data-agent
```

### 2. Create and activate the conda environment

```bash
make create-env
make activate-env
```

### 3. Install dependencies

```bash
make install-dependencies
```

### 4. Authenticate with Google Cloud

```bash
make initialize-gcp     # gcloud init
make login-gcp          # gcloud auth application-default login
```

### 5. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```dotenv
# .env
ANTHROPIC_VERTEX_PROJECT_ID=your-gcp-project-id  # GCP project for BigQuery, Firestore, and Vertex AI
CLOUD_ML_REGION=us-central1                       # optional, defaults to us-central1
LANGFUSE_PUBLIC_KEY=your-langfuse-public-key
LANGFUSE_SECRET_KEY=your-langfuse-secret-key
LANGFUSE_HOST=https://cloud.langfuse.com          # or your self-hosted URL
```

### 6. (Optional) Install pre-commit hooks

```bash
pre-commit install
```

---

## Running the API

```bash
make api
```

This starts `uvicorn` on `http://localhost:8000`. At startup the server:
1. Discovers and syncs plugins from `plugins/` into `.claude/`
2. Initializes the BigQuery and Firestore adapters
3. Fetches the BigQuery table schema and injects it into the agent's system prompt

**Default dataset configuration** (in `utils/file_paths.py`):
- Dataset: `tableau_sample_datasets`
- Table: `superstore_sales`
- Location: `us-central1`
- Firestore database: `claude-skills-data-agent`

---

## API Reference

All endpoints are prefixed with `/api/v0`.

### `GET /api/v0/health`

Health check.

```json
// Response 200
{ "status": "healthy" }
```

---

### `POST /api/v0/chat`

Submit a natural language question to the agent.

**Request body:**

```json
{
  "question": "What are the total sales by region?",
  "session_id": "uuid-for-session-continuation",
  "checkpoint_dir": "optional-path-to-checkpoint-directory",
  "user_id": "uuid-for-user-identifier"
}
```

- `question`: the natural language question
- `session_id`: UUID for session
- `checkpoint_dir`: path for storing local conversation checkpoints
- `user_id`: UUID for user

**Response:**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "result": "Total sales by region:\n- West: $725,457\n- East: $678,781\n..."
}
```

---

### `GET /api/v0/conversation-history`

Retrieve all messages in a session.

**Query params:** `session_id=<uuid>`

**Response:**

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "messages": [
    {
      "type": "human",
      "uuid": "...",
      "session_id": "...",
      "message": { "role": "user", "content": "What are total sales?" }
    }
  ]
}
```

---

### `DELETE /api/v0/clean-up`

Delete local checkpoint files for the current session.

```json
// Response 200
{ "status": "cleaned" }

// Response 200 (nothing to delete)
{ "status": "nothing to clean" }
```

---

## Testing

```bash
python -m pytest
```

Test files mirror the source structure under `tests/medium_claude_sdk_skills_data_agent/`. The CI pipeline (`.github/workflows/ci.yaml`) runs the full test suite on every push and pull request.

---

## Code Quality

```bash
make lint-code    # runs isort + black + ruff
```

Pre-commit hooks enforce formatting and linting on every commit. Configuration lives in `.pre-commit-config.yaml` and `pyproject.toml`.
