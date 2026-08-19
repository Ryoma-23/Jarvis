from typing import Any, Mapping

from app.services.conversation_store import ConversationStore


DEFAULT_CONTEXT_TURN_LIMIT = 15
CONVERSATION_SOURCES = frozenset({"text", "voice"})
CONTEXT_STATUSES = frozenset({"completed"})
CONTEXT_ROLES = frozenset({"user", "assistant"})
DISPLAY_ROLES = frozenset({"user", "assistant"})
DISPLAY_SOURCES = frozenset({"text", "voice"})
HIDDEN_METADATA_KEY = "hidden"
TOOL_METADATA_KEY = "tool"


class ConversationService:
    """Common conversation manager shared by future text and voice paths."""

    def __init__(self, store: ConversationStore | None = None):
        self.store = store or ConversationStore()

    def get_active_conversation(self) -> dict[str, Any] | None:
        return self.store.get_active_conversation()

    def get_or_create_active_conversation(
        self,
        *,
        title: str | None = None,
    ) -> dict[str, Any]:
        return self.store.get_or_create_active_conversation(title=title)

    def create_active_conversation(
        self,
        *,
        title: str | None = None,
    ) -> dict[str, Any]:
        return self.store.create_conversation(
            title=title,
            make_active=True,
        )

    def set_active_conversation(
        self,
        conversation_id: str,
    ) -> dict[str, Any]:
        return self.store.set_active_conversation(conversation_id)

    def add_user_message(
        self,
        content: str,
        *,
        source: str,
        item_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        _validate_source(source)
        _validate_completed_content(content)

        return self._add_message_to_conversation(
            role="user",
            content=content,
            source=source,
            status="completed",
            item_id=item_id,
            metadata=metadata,
            conversation_id=conversation_id,
        )

    def add_assistant_message(
        self,
        content: str,
        *,
        source: str,
        status: str = "completed",
        item_id: str | None = None,
        response_id: str | None = None,
        error_message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        _validate_source(source)

        if status == "completed":
            _validate_completed_content(content)

        return self._add_message_to_conversation(
            role="assistant",
            content=content,
            source=source,
            status=status,
            item_id=item_id,
            response_id=response_id,
            error_message=error_message,
            metadata=metadata,
            conversation_id=conversation_id,
        )

    def update_assistant_message(
        self,
        message_id: str,
        status: str,
        *,
        content: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        message = self.store.get_message(message_id)

        if message is None or message["role"] != "assistant":
            raise ValueError("message_id must identify an assistant message")

        if status == "completed":
            final_content = message["content"] if content is None else content
            _validate_completed_content(final_content)

        return self.store.update_message_status(
            message_id,
            status,
            content=content,
            error_message=error_message,
        )

    def record_realtime_user_transcript(
        self,
        content: str,
        *,
        item_id: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_item_id = _normalize_external_id(item_id, "item_id")
        message = self.add_user_message(
            content,
            source="voice",
            item_id=normalized_item_id,
            conversation_id=conversation_id,
        )

        if message["role"] != "user" or message["source"] != "voice":
            raise ValueError(
                "item_id must identify a voice user message"
            )

        return message

    def record_realtime_assistant_transcript(
        self,
        content: str,
        *,
        item_id: str | None = None,
        response_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        _validate_completed_content(content)
        item_id, response_id = _normalize_external_ids(
            item_id=item_id,
            response_id=response_id,
        )

        with self.store.transaction() as connection:
            conversation_id = self._resolve_conversation_id(
                conversation_id,
                connection=connection,
            )
            existing = self.store.get_message_by_external_ids(
                item_id=item_id,
                response_id=response_id,
                connection=connection,
            )

            if existing is None:
                return self.store.add_message(
                    conversation_id,
                    role="assistant",
                    content=content,
                    source="voice",
                    status="completed",
                    item_id=item_id,
                    response_id=response_id,
                    connection=connection,
                )

            self._validate_realtime_assistant_message(
                existing,
                conversation_id=conversation_id,
            )
            existing = self.store.add_message(
                conversation_id,
                role="assistant",
                content=existing["content"],
                source="voice",
                status=existing["status"],
                item_id=item_id,
                response_id=response_id,
                connection=connection,
            )

            if existing["status"] == "pending":
                return self.store.update_message_status(
                    existing["id"],
                    "completed",
                    content=content,
                    connection=connection,
                )

            if (
                existing["status"] == "interrupted"
                and not existing["content"].strip()
            ):
                return self.store.update_message_status(
                    existing["id"],
                    "interrupted",
                    content=content,
                    connection=connection,
                )

            return existing

    def interrupt_realtime_assistant_message(
        self,
        *,
        content: str = "",
        item_id: str | None = None,
        response_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        item_id, response_id = _normalize_external_ids(
            item_id=item_id,
            response_id=response_id,
        )

        with self.store.transaction() as connection:
            conversation_id = self._resolve_conversation_id(
                conversation_id,
                connection=connection,
            )
            existing = self.store.get_message_by_external_ids(
                item_id=item_id,
                response_id=response_id,
                connection=connection,
            )

            if existing is None:
                return self.store.add_message(
                    conversation_id,
                    role="assistant",
                    content=content,
                    source="voice",
                    status="interrupted",
                    item_id=item_id,
                    response_id=response_id,
                    connection=connection,
                )

            self._validate_realtime_assistant_message(
                existing,
                conversation_id=conversation_id,
            )
            existing = self.store.add_message(
                conversation_id,
                role="assistant",
                content=existing["content"],
                source="voice",
                status=existing["status"],
                item_id=item_id,
                response_id=response_id,
                connection=connection,
            )
            interrupted_content = (
                content if content.strip() else existing["content"]
            )
            return self.store.update_message_status(
                existing["id"],
                "interrupted",
                content=interrupted_content,
                connection=connection,
            )

    def record_hidden_tool_metadata(
        self,
        *,
        tool_name: str,
        call_id: str,
        arguments: Mapping[str, Any],
        result: Any,
        item_id: str | None = None,
        status: str = "completed",
        error_message: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        if not tool_name.strip():
            raise ValueError("tool_name must not be empty")

        if not call_id.strip():
            raise ValueError("call_id must not be empty")

        tool_metadata = {
            HIDDEN_METADATA_KEY: True,
            TOOL_METADATA_KEY: {
                "name": tool_name,
                "call_id": call_id,
                "arguments": dict(arguments),
                "result": result,
            },
        }

        return self._add_message_to_conversation(
            role="tool",
            content="",
            source="tool",
            status=status,
            item_id=item_id,
            error_message=error_message,
            metadata=tool_metadata,
            conversation_id=conversation_id,
        )

    def get_hidden_tool_metadata(
        self,
        *,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        messages = self._get_conversation_messages(conversation_id)
        return [
            message
            for message in messages
            if message["role"] == "tool" and _is_hidden(message)
        ]

    def get_display_messages(
        self,
        *,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return messages that are safe and relevant for the chat UI."""
        messages = self._get_conversation_messages(conversation_id)
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

        return [
            {
                field: message[field]
                for field in display_fields
            }
            for message in messages
            if message["role"] in DISPLAY_ROLES
            and message["source"] in DISPLAY_SOURCES
            and message["content"].strip()
            and not _is_hidden(message)
        ]

    def build_context(
        self,
        *,
        conversation_id: str | None = None,
        turn_limit: int = DEFAULT_CONTEXT_TURN_LIMIT,
    ) -> list[dict[str, str]]:
        messages = self._get_context_messages(
            conversation_id=conversation_id,
            turn_limit=turn_limit,
        )
        return [
            {
                "role": message["role"],
                "content": message["content"],
            }
            for message in messages
        ]

    def build_realtime_restore_events(
        self,
        *,
        conversation_id: str | None = None,
        turn_limit: int = DEFAULT_CONTEXT_TURN_LIMIT,
    ) -> list[dict[str, Any]]:
        messages = self._get_context_messages(
            conversation_id=conversation_id,
            turn_limit=turn_limit,
        )
        events = []

        for message in messages:
            content_type = (
                "input_text" if message["role"] == "user" else "output_text"
            )
            item = {
                "type": "message",
                "role": message["role"],
                "content": [
                    {
                        "type": content_type,
                        "text": message["content"],
                    }
                ],
            }

            if message["role"] == "assistant":
                item["status"] = "completed"

            events.append(
                {
                    "type": "conversation.item.create",
                    "item": item,
                }
            )

        return events

    def _add_message_to_conversation(
        self,
        *,
        role: str,
        content: str,
        source: str,
        status: str,
        item_id: str | None = None,
        response_id: str | None = None,
        error_message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        with self.store.transaction() as connection:
            conversation_id = self._resolve_conversation_id(
                conversation_id,
                connection=connection,
            )

            return self.store.add_message(
                conversation_id,
                role=role,
                content=content,
                source=source,
                status=status,
                item_id=item_id,
                response_id=response_id,
                error_message=error_message,
                metadata=metadata,
                connection=connection,
            )

    def _resolve_conversation_id(
        self,
        conversation_id: str | None,
        *,
        connection,
    ) -> str:
        if conversation_id is not None:
            return conversation_id

        conversation = self.store.get_or_create_active_conversation(
            connection=connection
        )
        return conversation["id"]

    @staticmethod
    def _validate_realtime_assistant_message(
        message: Mapping[str, Any],
        *,
        conversation_id: str,
    ) -> None:
        if message["conversation_id"] != conversation_id:
            raise ValueError(
                "Realtime message belongs to another conversation"
            )

        if message["role"] != "assistant" or message["source"] != "voice":
            raise ValueError(
                "External IDs must identify a voice assistant message"
            )

    def _get_context_messages(
        self,
        *,
        conversation_id: str | None,
        turn_limit: int,
    ) -> list[dict[str, Any]]:
        if turn_limit < 1:
            raise ValueError("turn_limit must be at least 1")

        messages = self._get_conversation_messages(conversation_id)
        eligible_messages = [
            message
            for message in messages
            if message["role"] in CONTEXT_ROLES
            and message["status"] in CONTEXT_STATUSES
            and message["content"].strip()
            and not _is_hidden(message)
        ]
        user_message_indexes = [
            index
            for index, message in enumerate(eligible_messages)
            if message["role"] == "user"
        ]

        if not user_message_indexes:
            return []

        included_turns = min(turn_limit, len(user_message_indexes))
        first_index = user_message_indexes[-included_turns]
        return eligible_messages[first_index:]

    def _get_conversation_messages(
        self,
        conversation_id: str | None,
    ) -> list[dict[str, Any]]:
        if conversation_id is None:
            conversation = self.store.get_active_conversation()

            if conversation is None:
                return []

            conversation_id = conversation["id"]

        return self.store.get_messages(conversation_id)


def _validate_source(source: str) -> None:
    if source not in CONVERSATION_SOURCES:
        raise ValueError("source must be either text or voice")


def _validate_completed_content(content: str) -> None:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("completed message content must not be empty")


def _normalize_external_id(value: str, name: str) -> str:
    normalized = str(value or "").strip()

    if not normalized:
        raise ValueError(f"{name} must not be empty")

    return normalized


def _normalize_external_ids(
    *,
    item_id: str | None,
    response_id: str | None,
) -> tuple[str | None, str | None]:
    normalized_item_id = (
        _normalize_external_id(item_id, "item_id")
        if item_id is not None
        else None
    )
    normalized_response_id = (
        _normalize_external_id(response_id, "response_id")
        if response_id is not None
        else None
    )

    if normalized_item_id is None and normalized_response_id is None:
        raise ValueError("item_id or response_id is required")

    return normalized_item_id, normalized_response_id


def _is_hidden(message: Mapping[str, Any]) -> bool:
    return message["metadata"].get(HIDDEN_METADATA_KEY) is True
