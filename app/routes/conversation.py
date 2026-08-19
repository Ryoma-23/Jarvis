from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.chat_service import get_conversation_service
from app.services.conversation_store import ConversationNotFoundError


router = APIRouter(prefix="/conversations")


class CreateConversationRequest(BaseModel):
    title: str | None = None


@router.get("/active")
def get_active_conversation():
    conversation_service = get_conversation_service()
    return {
        "conversation": conversation_service.get_active_conversation(),
    }


@router.get("/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str):
    conversation_service = get_conversation_service()

    try:
        messages = conversation_service.get_display_messages(
            conversation_id=conversation_id,
        )
    except ConversationNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        ) from error

    return {
        "conversation_id": conversation_id,
        "messages": messages,
    }


@router.post("")
def create_conversation(request: CreateConversationRequest):
    conversation_service = get_conversation_service()
    conversation = conversation_service.create_active_conversation(
        title=request.title,
    )
    return {"conversation": conversation}
