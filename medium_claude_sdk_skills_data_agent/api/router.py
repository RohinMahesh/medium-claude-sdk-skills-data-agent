import os
import shutil
import uuid

from claude_agent_sdk._internal.sessions import (
    _canonicalize_path,
    _find_project_dir,
    get_session_messages,
)
from fastapi import APIRouter, HTTPException, Request

from medium_claude_sdk_skills_data_agent.utils.file_paths import BASE_DIR
from medium_claude_sdk_skills_data_agent.utils.objects import (
    AgentRequest,
    AgentResponse,
    ConversationHistoryResponse,
    ConversationMessage,
)

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "healthy"}


@router.delete("/clean-up")
async def clean_up(app_request: Request):
    """
    Deletes all session files for this project from ~/.claude/projects/ and
    removes all skill and command files synced to .claude/ at startup

    :param app_request: FastAPI request used to access shared app state
    :returns status message indicating resources were removed
    """
    project_dir = _find_project_dir(_canonicalize_path(os.path.dirname(BASE_DIR)))
    if project_dir is not None and project_dir.exists():
        shutil.rmtree(project_dir)
        project_dir.mkdir()
        app_request.app.state.plugin_sync.clean()
        return {"status": "cleaned"}
    return {"status": "nothing to clean"}


@router.get("/conversation-history", response_model=ConversationHistoryResponse)
async def conversation_history(
    user_id: str, session_id: str
) -> ConversationHistoryResponse:
    """
    Retrieves the full conversation history for a given user/session

    :param user_id: the user ID used to derive the thread ID
    :param session_id: the session ID used to derive the thread ID
    :returns conversation history response containing all messages for the session
    """
    thread_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{user_id}:{session_id}"))
    messages = get_session_messages(session_id=thread_id, directory=BASE_DIR)
    if not messages:
        raise HTTPException(
            status_code=404,
            detail=f"No conversation found for user_id: {user_id}, session_id: {session_id}",
        )
    return ConversationHistoryResponse(
        session_id=thread_id,
        messages=[
            ConversationMessage(
                type=m.type,
                uuid=m.uuid,
                session_id=m.session_id,
                message=m.message,
            )
            for m in messages
        ],
    )


@router.post("/chat", response_model=AgentResponse)
async def chat(request: AgentRequest, app_request: Request) -> AgentResponse:
    """
    Submits a natural-language question to the BigQuery agent

    :param request: the agent request containing the question and session metadata
    :param app_request: FastAPI request used to access shared app state
    :returns agent response containing the result and session ID
    """
    try:
        result, session_id = await app_request.app.state.agent_service.run(
            question=request.question,
            schema=app_request.app.state.schema,
            user_id=request.user_id,
            session_id=request.session_id,
            checkpoint_dir=request.checkpoint_dir,
        )
        return AgentResponse(session_id=session_id, result=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
