import json
import logging

from datetime import datetime
from functools import lru_cache
from typing import Any

from app.config import SYSTEM_PROMPT_PATH
from app.openai_client import client
from app.services.conversation_service import ConversationService
from app.services.intent_service import (
    handle_memory_intent,
    handle_note_intent,
    handle_task_intent,
)
from app.services.memory_service import format_memory_for_prompt
from app.services.router_service import route_message


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_conversation_service() -> ConversationService:
    return ConversationService()


def load_system_prompt():
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as file:
        return file.read()


def generate_chat_stream(
    message: str,
    conversation_id: str | None = None,
):
    conversation_service = get_conversation_service()
    active_conversation_id = _normalize_conversation_id(conversation_id)
    user_message_saved = False
    assistant_message_saved = False
    full_reply = ""
    response_id = None
    route = None

    try:
        if active_conversation_id is None:
            conversation = (
                conversation_service.get_or_create_active_conversation()
            )
        else:
            conversation = conversation_service.set_active_conversation(
                active_conversation_id
            )

        active_conversation_id = conversation["id"]
        user_message = conversation_service.add_user_message(
            message,
            source="text",
            conversation_id=active_conversation_id,
        )
        user_message_saved = True
        yield _sse_payload(
            {"user_message_id": user_message["id"]},
            active_conversation_id,
        )

        route = route_message(message)
        specialized_reply = _handle_specialized_intent(route, message)

        if specialized_reply is not None:
            full_reply = specialized_reply
            assistant_message = conversation_service.add_assistant_message(
                full_reply,
                source="text",
                metadata={"route": route, "kind": "intent_result"},
                conversation_id=active_conversation_id,
            )
            assistant_message_saved = True

            yield _sse_payload(
                {
                    "text": full_reply,
                    "assistant_message_id": assistant_message["id"],
                },
                active_conversation_id,
            )
            yield _sse_payload(
                {
                    "done": True,
                    "assistant_message_id": assistant_message["id"],
                },
                active_conversation_id,
            )
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")
        system_prompt = load_system_prompt()
        memory_context = format_memory_for_prompt()
        context = conversation_service.build_context(
            conversation_id=active_conversation_id
        )
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "system",
                "content": f"現在日時: {current_time}",
            },
            {
                "role": "system",
                "content": memory_context,
            },
        ] + context

        stream = client.responses.create(
            model="gpt-5-mini",
            input=messages,
            stream=True,
            reasoning={"effort": "low"},
        )

        for event in stream:
            event_response = getattr(event, "response", None)

            if response_id is None and event_response is not None:
                response_id = getattr(event_response, "id", None)

            if event.type == "response.output_text.delta":
                text = event.delta
                full_reply += text
                yield _sse_payload(
                    {"text": text},
                    active_conversation_id,
                )

            if event.type in {"response.failed", "response.incomplete"}:
                raise RuntimeError(_response_failure_message(event))

        assistant_message = conversation_service.add_assistant_message(
            full_reply,
            source="text",
            response_id=response_id,
            metadata={"route": route or "chat"},
            conversation_id=active_conversation_id,
        )
        assistant_message_saved = True

        yield _sse_payload(
            {
                "done": True,
                "assistant_message_id": assistant_message["id"],
            },
            active_conversation_id,
        )

    except GeneratorExit:
        _persist_failed_assistant_message(
            conversation_service=conversation_service,
            conversation_id=active_conversation_id,
            should_persist=user_message_saved and not assistant_message_saved,
            content=full_reply,
            response_id=response_id,
            error_message="chat stream closed before completion",
            route=route,
        )
        raise

    except Exception as error:
        failed_message = _persist_failed_assistant_message(
            conversation_service=conversation_service,
            conversation_id=active_conversation_id,
            should_persist=user_message_saved and not assistant_message_saved,
            content=full_reply,
            response_id=response_id,
            error_message=str(error),
            route=route,
        )

        yield _sse_payload(
            {
                "error": str(error),
                "assistant_message_id": (
                    failed_message["id"]
                    if failed_message is not None
                    else None
                ),
            },
            active_conversation_id,
        )


def _persist_failed_assistant_message(
    *,
    conversation_service: ConversationService,
    conversation_id: str | None,
    should_persist: bool,
    content: str,
    response_id: str | None,
    error_message: str,
    route: str | None,
) -> dict[str, Any] | None:
    if should_persist and conversation_id is not None:
        try:
            return conversation_service.add_assistant_message(
                content,
                source="text",
                status="failed",
                response_id=response_id,
                error_message=error_message,
                metadata={"route": route or "unknown"},
                conversation_id=conversation_id,
            )
        except Exception:
            logger.exception("Failed to persist failed chat response")

    return None


def _handle_specialized_intent(route: str | None, message: str) -> str | None:
    if route == "note":
        return handle_note_intent(message)

    if route == "task":
        return handle_task_intent(message)

    if route == "memory":
        return handle_memory_intent(message)

    return None


def _normalize_conversation_id(conversation_id: str | None) -> str | None:
    if conversation_id is None:
        return None

    normalized = conversation_id.strip()
    return normalized or None


def _sse_payload(
    payload: dict[str, Any],
    conversation_id: str | None,
) -> str:
    data = dict(payload)

    if conversation_id is not None:
        data["conversation_id"] = conversation_id

    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _response_failure_message(event: Any) -> str:
    response = getattr(event, "response", None)
    error = getattr(response, "error", None)
    message = getattr(error, "message", None)

    if message:
        return message

    return f"Responses API stream ended with {event.type}"
