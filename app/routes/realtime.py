from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.chat_service import get_conversation_service
from app.services.conversation_store import (
    ConversationNotFoundError,
    DuplicateMessageError,
)
from app.services.realtime_service import create_realtime_token
from app.services.realtime_tool_service import execute_realtime_tool


router = APIRouter()


class RealtimeToolRequest(BaseModel):
    tool_name: str
    arguments: dict


class RealtimeVoiceMessageRequest(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    conversation_id: str | None = None
    item_id: str | None = None
    response_id: str | None = None


class RealtimeAssistantInterruptedRequest(BaseModel):
    content: str = ""
    conversation_id: str | None = None
    item_id: str | None = None
    response_id: str | None = None


@router.get("/realtime/token")
def get_realtime_token():
    return create_realtime_token()


@router.post("/realtime/tools")
def execute_tool(request: RealtimeToolRequest):
    return execute_realtime_tool(request.tool_name, request.arguments)


@router.post("/realtime/conversation/messages")
def save_realtime_voice_message(request: RealtimeVoiceMessageRequest):
    conversation_service = get_conversation_service()

    try:
        if request.role == "user":
            message = conversation_service.record_realtime_user_transcript(
                request.content,
                item_id=request.item_id or "",
                conversation_id=request.conversation_id,
            )
        else:
            message = (
                conversation_service.record_realtime_assistant_transcript(
                    request.content,
                    item_id=request.item_id,
                    response_id=request.response_id,
                    conversation_id=request.conversation_id,
                )
            )
    except Exception as error:
        _raise_conversation_http_error(error)

    return _realtime_message_response(message)


@router.post("/realtime/conversation/assistant/interrupted")
def interrupt_realtime_assistant_message(
    request: RealtimeAssistantInterruptedRequest,
):
    conversation_service = get_conversation_service()

    try:
        message = conversation_service.interrupt_realtime_assistant_message(
            content=request.content,
            item_id=request.item_id,
            response_id=request.response_id,
            conversation_id=request.conversation_id,
        )
    except Exception as error:
        _raise_conversation_http_error(error)

    return _realtime_message_response(message)


def _realtime_message_response(message: dict) -> dict:
    display_fields = (
        "id",
        "conversation_id",
        "role",
        "content",
        "source",
        "status",
        "created_at",
        "updated_at",
    )
    return {
        "conversation_id": message["conversation_id"],
        "message": {
            field: message[field]
            for field in display_fields
        },
    }


def _raise_conversation_http_error(error: Exception) -> None:
    if isinstance(error, ConversationNotFoundError):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        ) from error

    if isinstance(error, DuplicateMessageError):
        raise HTTPException(
            status_code=409,
            detail="Realtime message ID conflict",
        ) from error

    if isinstance(error, ValueError):
        raise HTTPException(status_code=422, detail=str(error)) from error

    raise error
