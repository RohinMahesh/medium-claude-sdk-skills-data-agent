from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class AgentRequest(BaseModel):
    """
    Input request object for the chat endpoint
    """

    question: str = Field(..., description="The user question")
    user_id: str | None = Field(
        default=None, description="Identifier for the user making the request"
    )
    session_id: str | None = Field(
        default=None,
        description="UUID for the session",
    )
    checkpoint_dir: str | None = Field(
        default=None, description="Whether to continue from the checkpoint directory"
    )

    @field_validator("question", mode="before")
    def validate_non_empty(cls, v: str, info: ValidationInfo) -> str:
        """
        Validates that question is non-empty
        """
        if not v or v.strip() == "":
            raise ValueError(f"Field {info.field_name} cannot be empty or whitespace")
        return v


class AgentResponse(BaseModel):
    """
    Output response object for the chat endpoint
    """

    session_id: str = Field(..., description="UUID for the session")
    result: str = Field(..., description="The response from the agent")

    @field_validator("session_id", mode="before")
    def validate_valid_entries(cls, v: str, info: ValidationInfo) -> str:
        """
        Validates whether the inputs are valid
        """
        if not v or v.strip() == "":
            raise ValueError(
                f"Field {info.field_name} cannot be empty, whitespace or None"
            )
        return v


class ConversationMessage(BaseModel):
    """
    Claude Agent SDK messages object
    """

    type: str = Field(..., description="The type of the message")
    uuid: str = Field(..., description="Unique identifier for the message")
    session_id: str = Field(
        ..., description="UUID for the session this message belongs to"
    )
    message: dict[str, Any] = Field(..., description="The message payload")


class ConversationHistoryResponse(BaseModel):
    """
    Output response object for the get conversation history endpoint
    """

    session_id: str = Field(..., description="UUID for the session")
    messages: list[ConversationMessage] = Field(
        ..., description="List of messages in the conversation history"
    )
