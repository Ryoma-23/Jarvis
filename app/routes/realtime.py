from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.chat_service import get_conversation_service
from app.services.conversation_service import DEFAULT_CONTEXT_TURN_LIMIT
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


class RealtimeConversationMessageRequest(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    source: Literal["text", "voice"] = "voice"
    conversation_id: str | None = None
    item_id: str | None = None
    response_id: str | None = None


class RealtimeAssistantInterruptedRequest(BaseModel):
    content: str = ""
    source: Literal["text", "voice"] = "voice"
    conversation_id: str | None = None
    item_id: str | None = None
    response_id: str | None = None


@router.get("/realtime/token")
def get_realtime_token(conversation_id: str | None = None):
    conversation_service = get_conversation_service()

    try:
        conversation = _resolve_realtime_conversation(
            conversation_service,
            conversation_id,
        )
    except Exception as error:
        _raise_conversation_http_error(error)

    return create_realtime_token(conversation_id=conversation["id"])


@router.get("/realtime/conversation/history")
def get_realtime_conversation_history(conversation_id: str):
    conversation_service = get_conversation_service()

    try:
        events = conversation_service.build_realtime_restore_events(
            conversation_id=conversation_id,
            turn_limit=DEFAULT_CONTEXT_TURN_LIMIT,
        )
    except Exception as error:
        _raise_conversation_http_error(error)

    return {
        "conversation_id": conversation_id,
        "turn_limit": DEFAULT_CONTEXT_TURN_LIMIT,
        "events": events,
    }


@router.post("/realtime/tools")
def execute_tool(request: RealtimeToolRequest):
    return execute_realtime_tool(request.tool_name, request.arguments)


@router.post("/realtime/conversation/messages")
def save_realtime_conversation_message(
    request: RealtimeConversationMessageRequest,
):
    conversation_service = get_conversation_service()

    try:
        if request.role == "user":
            message = conversation_service.record_realtime_user_message(
                request.content,
                source=request.source,
                item_id=request.item_id or "",
                conversation_id=request.conversation_id,
            )
        else:
            message = (
                conversation_service.record_realtime_assistant_message(
                    request.content,
                    source=request.source,
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
            source=request.source,
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


def _resolve_realtime_conversation(
    conversation_service,
    conversation_id: str | None,
) -> dict:
    if conversation_id is None:
        return conversation_service.get_or_create_active_conversation()

    conversation = conversation_service.get_conversation(conversation_id)

    if conversation is None:
        raise ConversationNotFoundError(conversation_id)

    return conversation


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
