import json
import os
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, ClassVar

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookContext,
    HookMatcher,
    PostToolUseFailureHookInput,
    PostToolUseHookInput,
    PreCompactHookInput,
    PreToolUseHookInput,
    create_sdk_mcp_server,
    get_session_messages,
)
from claude_agent_sdk.types import SyncHookJSONOutput
from langfuse import get_client
from langfuse.types import TraceContext

from medium_claude_sdk_skills_data_agent.adapters.bigquery_adapter import create_bq_tool
from medium_claude_sdk_skills_data_agent.core.ports import (
    AgentServicePort,
    BigQueryPort,
    PersistencePort,
)
from medium_claude_sdk_skills_data_agent.utils.constants import (
    AGENT_DESCRIPTION,
    AGENT_NAME,
    CLAUDE_SETTINGS_JSON,
    DEFAULT_MODEL,
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
    TOOL_NAME,
)
from medium_claude_sdk_skills_data_agent.utils.file_paths import DATASET_ID
from medium_claude_sdk_skills_data_agent.utils.helpers import create_logger
from medium_claude_sdk_skills_data_agent.utils.prompts import AGENT_PROMPT_TEMPLATE


@dataclass
class AgentService(AgentServicePort):
    """
    Core agent service that orchestrates the Claude Agent SDK

    :param bq_port: port for executing BigQuery operations
    :param skills: list of Claude Code skill names to enable for the agent
    :param firestore_store: optional persistence port for saving and restoring session state
    :param _mcp_server: MCP server instance exposing the BigQuery tool to the agent
    :param _agent: agent definition containing the prompt, tools, and model configuration
    :param _active_tool_spans: map of tool use ID to in-flight Langfuse observation spans
    :param _active_tool_starts: map of tool use ID to monotonic start time for duration tracking
    :param _ctx_trace_id: context variable holding the Langfuse trace ID for the current request
    :param _ctx_run_span_id: context variable holding the Langfuse run span ID for the current request
    """

    bq_port: BigQueryPort
    skills: list[str] = field(default_factory=list)
    firestore_store: PersistencePort | None = field(default=None)
    _mcp_server: object = field(init=False, repr=False)
    _agent: AgentDefinition = field(init=False, repr=False)
    _active_tool_spans: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False
    )
    _active_tool_starts: dict[str, float] = field(
        default_factory=dict, init=False, repr=False
    )
    _ctx_trace_id: ClassVar[ContextVar[str]] = ContextVar("langfuse_trace_id")
    _ctx_run_span_id: ClassVar[ContextVar[str]] = ContextVar("langfuse_run_span_id")

    def __post_init__(self):
        """
        Initializes the MCP server, agent definition, and Langfuse client
        """
        self.logger = create_logger(name="AgentService")
        self.langfuse = get_client()

        self.project_id = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
        self.dataset_id = DATASET_ID

        bq_tool = create_bq_tool(bq_port=self.bq_port)
        self._mcp_server = create_sdk_mcp_server(
            name=MCP_SERVER_NAME,
            version=MCP_SERVER_VERSION,
            tools=[bq_tool],
        )

    async def _pre_tool_hook(
        self,
        hook_input: PreToolUseHookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> SyncHookJSONOutput:
        """
        Execution of pre tool hook in Claude Agent SDK

        :param hook_input: pre-tool-use hook payload containing tool name, ID, and input
        :param _tool_use_id: tool use ID passed by the SDK hook dispatcher
        :param _context: hook context passed by the SDK hook dispatcher
        :returns SyncHookJSONOutput indicating the SDK should continue execution
        """
        tool_use_id = hook_input["tool_use_id"]
        self._active_tool_starts[tool_use_id] = time.monotonic()
        span = self.langfuse.start_observation(
            trace_context=TraceContext(
                trace_id=AgentService._ctx_trace_id.get(),
                parent_span_id=AgentService._ctx_run_span_id.get(),
            ),
            as_type="tool",
            name=hook_input["tool_name"],
            input=hook_input["tool_input"],
        )
        self._active_tool_spans[tool_use_id] = span
        return {"continue_": True}

    async def _post_tool_hook(
        self,
        hook_input: PostToolUseHookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> SyncHookJSONOutput:
        """
        Execution of post tool hook in Claude Agent SDK

        :param hook_input: post-tool-use hook payload containing tool ID and response
        :param _tool_use_id: tool use ID passed by the SDK hook dispatcher
        :param _context: hook context passed by the SDK hook dispatcher
        :returns SyncHookJSONOutput indicating the SDK should continue execution
        """
        tool_use_id = hook_input["tool_use_id"]
        duration_ms = round(
            (
                time.monotonic()
                - self._active_tool_starts.pop(tool_use_id, time.monotonic())
            )
            * 1000,
            2,
        )
        span = self._active_tool_spans.pop(tool_use_id, None)
        if span is not None:
            span.update(
                output=hook_input["tool_response"],
                metadata={"duration_ms": duration_ms},
            )
            span.end()
        return {"continue_": True}

    async def _post_tool_failure_hook(
        self,
        hook_input: PostToolUseFailureHookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> SyncHookJSONOutput:
        """
        Execution of post tool hook failures in Claude Agent SDK

        :param hook_input: post-tool-use failure payload containing tool ID and error details
        :param _tool_use_id: tool use ID passed by the SDK hook dispatcher
        :param _context: hook context passed by the SDK hook dispatcher
        :returns SyncHookJSONOutput indicating the SDK should continue execution
        """
        tool_use_id = hook_input["tool_use_id"]
        duration_ms = round(
            (
                time.monotonic()
                - self._active_tool_starts.pop(tool_use_id, time.monotonic())
            )
            * 1000,
            2,
        )
        span = self._active_tool_spans.pop(tool_use_id, None)
        if span is not None:
            span.update(
                output={"error": hook_input["error"]},
                level="ERROR",
                metadata={"duration_ms": duration_ms},
            )
            span.end()
        return {"continue_": True}

    async def _pre_compact_hook(
        self,
        hook_input: PreCompactHookInput,
        _tool_use_id: str | None,
        _context: HookContext,
    ) -> SyncHookJSONOutput:
        """
        Execution of pre compaction hook in Claude Agent SDK

        :param hook_input: pre-compact hook payload containing the compaction trigger reason
        :param _tool_use_id: tool use ID passed by the SDK hook dispatcher
        :param _context: hook context passed by the SDK hook dispatcher
        :returns SyncHookJSONOutput indicating the SDK should continue execution
        """
        self.logger.info(f"Context compaction triggered (trigger={hook_input.trigger})")
        return {"continue_": True}

    @staticmethod
    def _ensure_compaction_settings(working_directory: str):
        """
        Ensures that compaction settings are copied to root

        :param working_directory: the current working directory
        """
        settings_path = os.path.join(working_directory, ".claude", "settings.json")
        try:
            with open(settings_path) as f:
                existing = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing = {}
        if not all(existing.get(k) == v for k, v in CLAUDE_SETTINGS_JSON.items()):
            existing.update(CLAUDE_SETTINGS_JSON)
            os.makedirs(os.path.dirname(settings_path), exist_ok=True)
            with open(settings_path, "w") as f:
                json.dump(existing, f, indent=2)

    async def run(
        self,
        question: str,
        schema: str,
        user_id: str,
        session_id: str,
        checkpoint_dir: str | None = None,
    ) -> tuple[str, str]:
        """
        Runs the BigQuery agent with the given question

        :param question: the user question to answer
        :param schema: pre-fetched formatted table schema string
        :param user_id: identifier for the user; used as the Firestore collection ID
        :param session_id: the session ID
        :param checkpoint_dir: optional directory for checkpoint files
        :returns tuple of (result_text, session_id)
        """
        if checkpoint_dir is None:
            checkpoint_dir = os.getcwd()

        self._ensure_compaction_settings(working_directory=checkpoint_dir)

        thread_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{user_id}:{session_id}"))

        # Define LangFuse Trace ID
        langfuse_trace_id = self.langfuse.create_trace_id(seed=thread_id)

        # Create the run-level span explicitly which is request-scoped via ContextVars
        run_span = self.langfuse.start_observation(
            trace_context=TraceContext(trace_id=langfuse_trace_id),
            as_type="span",
            name="bq-agent-run",
            input=question,
            metadata={"user_id": user_id, "session_id": session_id},
        )
        AgentService._ctx_trace_id.set(langfuse_trace_id)
        AgentService._ctx_run_span_id.set(run_span.id)

        client = None
        result = ""
        try:
            # Restore session state from Firestore if present
            if self.firestore_store is not None:
                _fs_data = await self.firestore_store.load_session(
                    user_id=user_id, thread_id=thread_id
                )
                if _fs_data is not None:
                    await self.firestore_store.restore_checkpoint(
                        thread_id=thread_id,
                        messages=_fs_data,
                        checkpoint_dir=checkpoint_dir,
                    )

            # Define agent
            _agent = AgentDefinition(
                description=AGENT_DESCRIPTION,
                prompt=AGENT_PROMPT_TEMPLATE.format(
                    schema=schema,
                    tool=f"mcp__{MCP_SERVER_NAME}__{TOOL_NAME}",
                ),
                tools=[f"mcp__{MCP_SERVER_NAME}__{TOOL_NAME}"],
                skills=self.skills or None,
                model=DEFAULT_MODEL,
            )

            vertex_env = {}
            if project_id := os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID"):
                vertex_env["ANTHROPIC_VERTEX_PROJECT_ID"] = project_id
            if region := os.environ.get("CLOUD_ML_REGION"):
                vertex_env["CLOUD_ML_REGION"] = region

            # Identify new session
            _resume_id = thread_id
            _session_exists = bool(
                get_session_messages(session_id=_resume_id, directory=checkpoint_dir)
            )

            client = ClaudeSDKClient(
                options=ClaudeAgentOptions(
                    allowed_tools=[f"mcp__{MCP_SERVER_NAME}__{TOOL_NAME}"],
                    mcp_servers={MCP_SERVER_NAME: self._mcp_server},
                    agents={AGENT_NAME: _agent},
                    enable_file_checkpointing=True,
                    session_id=thread_id if not _session_exists else None,
                    max_turns=5,
                    continue_conversation=_session_exists,
                    resume=_resume_id if _session_exists else None,
                    cwd=checkpoint_dir,
                    env=vertex_env if vertex_env else None,
                    setting_sources=["project"],
                    hooks={
                        "PreToolUse": [HookMatcher(hooks=[self._pre_tool_hook])],
                        "PostToolUse": [HookMatcher(hooks=[self._post_tool_hook])],
                        "PostToolUseFailure": [
                            HookMatcher(hooks=[self._post_tool_failure_hook])
                        ],
                        "PreCompact": [HookMatcher(hooks=[self._pre_compact_hook])],
                    },
                )
            )

            await client.connect()
            self.logger.info(f"Session {thread_id} executing question: {question}")
            await client.query(prompt=question, session_id=thread_id)

            async for message in client.receive_messages():
                if hasattr(message, "result"):
                    result = str(message.result)
                    break
            else:
                self.logger.warning(f"Session {thread_id} received no result message")

            usage = await client.get_context_usage()
            self.logger.info(
                f"Context: {usage['percentage']:.1f}% used, "
                f"threshold={usage.get('autoCompactThreshold')}, "
                f"autoCompact={usage.get('isAutoCompactEnabled')}"
            )

            run_span.update(
                output=result,
                metadata={
                    "user_id": user_id,
                    "session_id": session_id,
                    "context_pct": usage.get("percentage"),
                    "auto_compact": usage.get("isAutoCompactEnabled"),
                },
            )

            # Sync the latest checkpoint file back to Firestore
            if self.firestore_store is not None:
                await self.firestore_store.save_session(
                    user_id=user_id,
                    thread_id=thread_id,
                    checkpoint_dir=checkpoint_dir,
                )

            self.logger.info(f"Session {thread_id} successful response: {result}")
            return result, thread_id
        except Exception as e:
            run_span.update(output={"error": str(e)}, level="ERROR")
            self.logger.error(f"Request failed with error: {e}")
            return "", session_id
        finally:
            run_span.end()
            self.langfuse.flush()
            if client is not None:
                await client.disconnect()
