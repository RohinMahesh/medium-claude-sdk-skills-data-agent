import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from medium_claude_sdk_skills_data_agent.adapters.bigquery_adapter import (
    BigQueryAdapter,
)
from medium_claude_sdk_skills_data_agent.adapters.firestore_adapter import (
    FirestoreSessionStore,
)
from medium_claude_sdk_skills_data_agent.adapters.plugin_adapter import PluginSync
from medium_claude_sdk_skills_data_agent.api.router import router
from medium_claude_sdk_skills_data_agent.core.agent import AgentService
from medium_claude_sdk_skills_data_agent.utils.file_paths import (
    BQ_LOCATION,
    CLAUDE_DIR,
    DATASET_ID,
    PLUGINS_DIR,
    TABLE_ID,
)
from medium_claude_sdk_skills_data_agent.utils.helpers import get_schema
from version import MAJOR, __version__

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application lifespan by making resources available for the duration of the application's life

    :param app: the FastAPI application instance used to store shared state
    """
    # Sync plugins
    plugin_sync = PluginSync(plugins_root=PLUGINS_DIR, claude_dir=CLAUDE_DIR)
    plugin_sync.sync()
    app.state.plugin_sync = plugin_sync

    # Initialize BigQuery and Firestore adapters
    bq_adapter = BigQueryAdapter(
        project_id=os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID"),
        location=BQ_LOCATION,
    )
    firestore_store = None
    if project_id := os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID"):
        firestore_store = FirestoreSessionStore(project_id=project_id)

    # Initialize AgentService and retreive table schema
    app.state.agent_service = AgentService(
        bq_port=bq_adapter,
        skills=plugin_sync.skill_names,
        firestore_store=firestore_store,
    )
    app.state.schema = await get_schema(
        project_id=os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID"),
        dataset_id=DATASET_ID,
        table_id=TABLE_ID,
    )
    yield


app = FastAPI(title="BigQuery Agent API", version=__version__, lifespan=lifespan)
app.include_router(router=router, prefix=f"/api/v{MAJOR}")
