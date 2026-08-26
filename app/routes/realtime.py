from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.chat_service import get_conversation_service
from app.services.conversation_retry_service import (
    ConversationPersistenceOutcome,
    persist_conversation_message,
)
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
        conversation_id = _resolve_realtime_message_conversation_id(
            conversation_service,
            request.conversation_id,
        )

        if request.role == "user":
            identity_key = (
                "realtime-user:"
                f"{conversation_id}:{request.item_id or ''}:"
                f"{request.source}:{request.content}"
            )
            outcome = persist_conversation_message(
                operation=lambda message_id: (
                    conversation_service.record_realtime_user_message(
                        request.content,
                        source=request.source,
                        item_id=request.item_id or "",
                        message_id=message_id,
                        conversation_id=conversation_id,
                    )
                ),
                conversation_id=conversation_id,
                role="user",
                content=request.content,
                source=request.source,
                status="completed",
                identity_key=identity_key,
            )
        else:
            identity_key = _realtime_assistant_identity_key(
                "completed",
                conversation_id=conversation_id,
                item_id=request.item_id,
                response_id=request.response_id,
                source=request.source,
                content=request.content,
            )
            outcome = persist_conversation_message(
                operation=lambda message_id: (
                    conversation_service.record_realtime_assistant_message(
                        request.content,
                        source=request.source,
                        item_id=request.item_id,
                        response_id=request.response_id,
                        message_id=message_id,
                        conversation_id=conversation_id,
                    )
                ),
                conversation_id=conversation_id,
                role="assistant",
                content=request.content,
                source=request.source,
                status="completed",
                identity_key=identity_key,
            )
    except Exception as error:
        _raise_conversation_http_error(error)

    return _realtime_message_response(outcome)


@router.post("/realtime/conversation/assistant/interrupted")
def interrupt_realtime_assistant_message(
    request: RealtimeAssistantInterruptedRequest,
):
    conversation_service = get_conversation_service()

    try:
        conversation_id = _resolve_realtime_message_conversation_id(
            conversation_service,
            request.conversation_id,
        )
        identity_key = _realtime_assistant_identity_key(
            "interrupted",
            conversation_id=conversation_id,
            item_id=request.item_id,
            response_id=request.response_id,
            source=request.source,
            content=request.content,
        )
        outcome = persist_conversation_message(
            operation=lambda message_id: (
                conversation_service.interrupt_realtime_assistant_message(
                    content=request.content,
                    item_id=request.item_id,
                    response_id=request.response_id,
                    source=request.source,
                    message_id=message_id,
                    conversation_id=conversation_id,
                )
            ),
            conversation_id=conversation_id,
            role="assistant",
            content=request.content,
            source=request.source,
            status="interrupted",
            identity_key=identity_key,
        )
    except Exception as error:
        _raise_conversation_http_error(error)

    return _realtime_message_response(outcome)


def _realtime_message_response(
    outcome: ConversationPersistenceOutcome,
) -> dict:
    message = outcome.message
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
    response = {
        "conversation_id": message["conversation_id"],
        "message": {
            field: message[field]
            for field in display_fields
        },
    }

    persistence = outcome.status_payload()

    if persistence is not None:
        response["persistence"] = persistence

    return response


def _resolve_realtime_message_conversation_id(
    conversation_service,
    conversation_id: str | None,
) -> str:
    normalized_conversation_id = str(conversation_id or "").strip()

    if normalized_conversation_id:
        return normalized_conversation_id

    conversation = _resolve_realtime_conversation(
        conversation_service,
        None,
    )
    return conversation["id"]


def _realtime_assistant_identity_key(
    action: str,
    *,
    conversation_id: str,
    item_id: str | None,
    response_id: str | None,
    source: str,
    content: str,
) -> str:
    external_id = response_id or item_id or "missing"
    return (
        f"realtime-assistant:{action}:{conversation_id}:{external_id}:"
        f"{source}:{content}"
    )


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
