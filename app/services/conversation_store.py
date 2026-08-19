import json
import sqlite3

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

from app.config import CONVERSATION_DB_FILE


MESSAGE_ROLES = frozenset({"user", "assistant", "system", "tool"})
MESSAGE_SOURCES = frozenset({"text", "voice", "tool", "system"})
MESSAGE_STATUSES = frozenset(
    {"pending", "completed", "interrupted", "failed"}
)


class ConversationStoreError(Exception):
    """Base exception for conversation persistence errors."""


class ConversationNotFoundError(ConversationStoreError):
    """Raised when a requested conversation does not exist."""


class MessageNotFoundError(ConversationStoreError):
    """Raised when a requested message does not exist."""


class DuplicateMessageError(ConversationStoreError):
    """Raised when external IDs point to conflicting messages."""


class ConversationStore:
    """SQLite persistence for conversations and their ordered messages."""

    def __init__(self, db_path: str | Path = CONVERSATION_DB_FILE):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize_schema(self) -> None:
        with self._read_connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    is_active INTEGER NOT NULL DEFAULT 0
                        CHECK (is_active IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_conversations_single_active
                ON conversations(is_active)
                WHERE is_active = 1;

                CREATE TABLE IF NOT EXISTS messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL
                        CHECK (role IN ('user', 'assistant', 'system', 'tool')),
                    content TEXT NOT NULL,
                    source TEXT NOT NULL
                        CHECK (source IN ('text', 'voice', 'tool', 'system')),
                    status TEXT NOT NULL
                        CHECK (
                            status IN (
                                'pending',
                                'completed',
                                'interrupted',
                                'failed'
                            )
                        ),
                    item_id TEXT,
                    response_id TEXT,
                    error_message TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id)
                        REFERENCES conversations(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation_sequence
                ON messages(conversation_id, sequence);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_item_id
                ON messages(item_id)
                WHERE item_id IS NOT NULL;

                CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_response_id
                ON messages(response_id)
                WHERE response_id IS NOT NULL;

                PRAGMA user_version = 1;
                """
            )
            connection.commit()

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()

        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Open an explicit write transaction that commits or rolls back."""

        connection = self._connect()

        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_conversation(
        self,
        *,
        conversation_id: str | None = None,
        title: str | None = None,
        make_active: bool = False,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        if connection is None:
            with self.transaction() as transaction:
                return self.create_conversation(
                    conversation_id=conversation_id,
                    title=title,
                    make_active=make_active,
                    connection=transaction,
                )

        conversation_id = conversation_id or uuid4().hex
        now = _utc_now()

        if make_active:
            connection.execute(
                "UPDATE conversations SET is_active = 0 WHERE is_active = 1"
            )

        connection.execute(
            """
            INSERT INTO conversations (
                id,
                title,
                is_active,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, title, int(make_active), now, now),
        )

        return self._get_conversation(connection, conversation_id)

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self._read_connection() as connection:
            return self._get_conversation(connection, conversation_id)

    def get_active_conversation(self) -> dict[str, Any] | None:
        with self._read_connection() as connection:
            return self._get_active_conversation(connection)

    def get_or_create_active_conversation(
        self,
        *,
        title: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        if connection is None:
            with self.transaction() as transaction:
                return self.get_or_create_active_conversation(
                    title=title,
                    connection=transaction,
                )

        conversation = self._get_active_conversation(connection)

        if conversation is not None:
            return conversation

        return self.create_conversation(
            title=title,
            make_active=True,
            connection=connection,
        )

    def set_active_conversation(
        self,
        conversation_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        if connection is None:
            with self.transaction() as transaction:
                return self.set_active_conversation(
                    conversation_id,
                    connection=transaction,
                )

        if self._get_conversation(connection, conversation_id) is None:
            raise ConversationNotFoundError(conversation_id)

        now = _utc_now()
        connection.execute(
            "UPDATE conversations SET is_active = 0 WHERE is_active = 1"
        )
        connection.execute(
            """
            UPDATE conversations
            SET is_active = 1, updated_at = ?
            WHERE id = ?
            """,
            (now, conversation_id),
        )

        return self._get_conversation(connection, conversation_id)

    def clear_active_conversation(
        self,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.transaction() as transaction:
                self.clear_active_conversation(connection=transaction)
                return

        connection.execute(
            "UPDATE conversations SET is_active = 0 WHERE is_active = 1"
        )

    def add_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        source: str,
        status: str = "completed",
        message_id: str | None = None,
        item_id: str | None = None,
        response_id: str | None = None,
        error_message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        _validate_choice("role", role, MESSAGE_ROLES)
        _validate_choice("source", source, MESSAGE_SOURCES)
        _validate_choice("status", status, MESSAGE_STATUSES)

        if connection is None:
            with self.transaction() as transaction:
                return self.add_message(
                    conversation_id,
                    role=role,
                    content=content,
                    source=source,
                    status=status,
                    message_id=message_id,
                    item_id=item_id,
                    response_id=response_id,
                    error_message=error_message,
                    metadata=metadata,
                    connection=transaction,
                )

        if self._get_conversation(connection, conversation_id) is None:
            raise ConversationNotFoundError(conversation_id)

        duplicate = self._find_duplicate_message(
            connection,
            item_id=item_id,
            response_id=response_id,
        )

        if duplicate is not None:
            if duplicate["conversation_id"] != conversation_id:
                raise DuplicateMessageError(
                    "External message ID already belongs to another conversation"
                )

            self._add_missing_external_ids(
                connection,
                duplicate,
                item_id=item_id,
                response_id=response_id,
            )
            return self._get_message(connection, duplicate["id"])

        message_id = message_id or uuid4().hex
        now = _utc_now()
        metadata_json = json.dumps(
            dict(metadata or {}),
            ensure_ascii=False,
            sort_keys=True,
        )

        connection.execute(
            """
            INSERT INTO messages (
                id,
                conversation_id,
                role,
                content,
                source,
                status,
                item_id,
                response_id,
                error_message,
                metadata_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation_id,
                role,
                content,
                source,
                status,
                item_id,
                response_id,
                error_message,
                metadata_json,
                now,
                now,
            ),
        )
        connection.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )

        return self._get_message(connection, message_id)

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        with self._read_connection() as connection:
            return self._get_message(connection, message_id)

    def get_message_by_item_id(self, item_id: str) -> dict[str, Any] | None:
        with self._read_connection() as connection:
            return self._get_message_by_external_id(
                connection,
                "item_id",
                item_id,
            )

    def get_message_by_response_id(
        self,
        response_id: str,
    ) -> dict[str, Any] | None:
        with self._read_connection() as connection:
            return self._get_message_by_external_id(
                connection,
                "response_id",
                response_id,
            )

    def get_messages(
        self,
        conversation_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")

        with self._read_connection() as connection:
            if self._get_conversation(connection, conversation_id) is None:
                raise ConversationNotFoundError(conversation_id)

            if limit is None:
                rows = connection.execute(
                    """
                    SELECT * FROM messages
                    WHERE conversation_id = ?
                    ORDER BY sequence ASC
                    """,
                    (conversation_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM messages
                        WHERE conversation_id = ?
                        ORDER BY sequence DESC
                        LIMIT ?
                    )
                    ORDER BY sequence ASC
                    """,
                    (conversation_id, limit),
                ).fetchall()

        return [_message_from_row(row) for row in rows]

    def update_message_status(
        self,
        message_id: str,
        status: str,
        *,
        content: str | None = None,
        error_message: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        _validate_choice("status", status, MESSAGE_STATUSES)

        if connection is None:
            with self.transaction() as transaction:
                return self.update_message_status(
                    message_id,
                    status,
                    content=content,
                    error_message=error_message,
                    connection=transaction,
                )

        message = self._get_message(connection, message_id)

        if message is None:
            raise MessageNotFoundError(message_id)

        now = _utc_now()
        next_content = message["content"] if content is None else content
        connection.execute(
            """
            UPDATE messages
            SET content = ?, status = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_content, status, error_message, now, message_id),
        )
        connection.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, message["conversation_id"]),
        )

        return self._get_message(connection, message_id)

    def _find_duplicate_message(
        self,
        connection: sqlite3.Connection,
        *,
        item_id: str | None,
        response_id: str | None,
    ) -> dict[str, Any] | None:
        matches: dict[str, dict[str, Any]] = {}

        for column, value in (
            ("item_id", item_id),
            ("response_id", response_id),
        ):
            if value is None:
                continue

            row = connection.execute(
                f"SELECT * FROM messages WHERE {column} = ?",
                (value,),
            ).fetchone()

            if row is not None:
                message = _message_from_row(row)
                matches[message["id"]] = message

        if len(matches) > 1:
            raise DuplicateMessageError(
                "item_id and response_id belong to different messages"
            )

        return next(iter(matches.values()), None)

    def _add_missing_external_ids(
        self,
        connection: sqlite3.Connection,
        message: dict[str, Any],
        *,
        item_id: str | None,
        response_id: str | None,
    ) -> None:
        if (
            item_id is not None
            and message["item_id"] is not None
            and item_id != message["item_id"]
        ):
            raise DuplicateMessageError(
                "response_id conflicts with the existing item_id"
            )

        if (
            response_id is not None
            and message["response_id"] is not None
            and response_id != message["response_id"]
        ):
            raise DuplicateMessageError(
                "item_id conflicts with the existing response_id"
            )

        next_item_id = message["item_id"] or item_id
        next_response_id = message["response_id"] or response_id

        if (
            next_item_id == message["item_id"]
            and next_response_id == message["response_id"]
        ):
            return

        connection.execute(
            """
            UPDATE messages
            SET item_id = ?, response_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_item_id, next_response_id, _utc_now(), message["id"]),
        )

    @staticmethod
    def _get_conversation(
        connection: sqlite3.Connection,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        return _conversation_from_row(row) if row is not None else None

    @staticmethod
    def _get_active_conversation(
        connection: sqlite3.Connection,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM conversations WHERE is_active = 1"
        ).fetchone()
        return _conversation_from_row(row) if row is not None else None

    @staticmethod
    def _get_message(
        connection: sqlite3.Connection,
        message_id: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        return _message_from_row(row) if row is not None else None

    @staticmethod
    def _get_message_by_external_id(
        connection: sqlite3.Connection,
        column: str,
        external_id: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            f"SELECT * FROM messages WHERE {column} = ?",
            (external_id,),
        ).fetchone()
        return _message_from_row(row) if row is not None else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _validate_choice(name: str, value: str, choices: frozenset[str]) -> None:
    if value not in choices:
        options = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of: {options}")


def _conversation_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _message_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "sequence": row["sequence"],
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "role": row["role"],
        "content": row["content"],
        "source": row["source"],
        "status": row["status"],
        "item_id": row["item_id"],
        "response_id": row["response_id"],
        "error_message": row["error_message"],
        "metadata": json.loads(row["metadata_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
