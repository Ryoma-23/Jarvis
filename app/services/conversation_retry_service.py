import logging
import sqlite3
import threading
import time

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4, uuid5


logger = logging.getLogger(__name__)

CONVERSATION_SAVE_MAX_RETRIES = 3
CONVERSATION_SAVE_RETRY_DELAY_SECONDS = 1.0
CONVERSATION_PERSISTENCE_STATUS_LIMIT = 256
CONVERSATION_MESSAGE_NAMESPACE = UUID(
    "e3bf0999-0af8-4a11-9035-e5a824761676"
)


@dataclass
class ConversationPersistenceOutcome:
    message: dict[str, Any]
    operation_id: str | None = None

    @property
    def pending(self) -> bool:
        return self.operation_id is not None

    def status_payload(self) -> dict[str, str] | None:
        if self.operation_id is None:
            return None

        return {
            "operation_id": self.operation_id,
            "status": "pending",
        }


@dataclass
class _RetryTask:
    operation_id: str
    scope_id: str
    callback: Callable[[], dict[str, Any]]
    attempts: int = 0
    next_attempt_at: float = 0.0


class ConversationPersistenceRetryQueue:
    """Process-local, non-blocking retry queue for SQLite message writes."""

    def __init__(
        self,
        *,
        max_retries: int = CONVERSATION_SAVE_MAX_RETRIES,
        retry_delay_seconds: float = CONVERSATION_SAVE_RETRY_DELAY_SECONDS,
        auto_start: bool = True,
    ):
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")

        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must not be negative")

        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.auto_start = auto_start
        self._condition = threading.Condition()
        self._tasks: deque[_RetryTask] = deque()
        self._statuses: dict[str, dict[str, Any]] = {}
        self._pending_scope_counts: dict[str, int] = {}
        self._worker: threading.Thread | None = None
        self._stopped = False

    def enqueue(
        self,
        operation_id: str,
        callback: Callable[[], dict[str, Any]],
        *,
        scope_id: str,
    ) -> bool:
        normalized_operation_id = str(operation_id or "").strip()

        if not normalized_operation_id:
            raise ValueError("operation_id must not be empty")

        if not str(scope_id or "").strip():
            raise ValueError("scope_id must not be empty")

        with self._condition:
            current = self._statuses.get(normalized_operation_id)

            if current and current["status"] in {"pending", "succeeded"}:
                return False

            self._statuses.pop(normalized_operation_id, None)
            self._statuses[normalized_operation_id] = {
                "operation_id": normalized_operation_id,
                "status": "pending",
                "attempts": 0,
                "max_retries": self.max_retries,
            }
            self._tasks.append(
                _RetryTask(
                    operation_id=normalized_operation_id,
                    scope_id=scope_id,
                    callback=callback,
                    next_attempt_at=time.monotonic(),
                )
            )
            self._pending_scope_counts[scope_id] = (
                self._pending_scope_counts.get(scope_id, 0) + 1
            )

            if self.auto_start:
                self._start_worker_locked()

            self._condition.notify_all()
            return True

    def has_pending(self, scope_id: str) -> bool:
        with self._condition:
            return self._pending_scope_counts.get(scope_id, 0) > 0

    def get_status(self, operation_id: str) -> dict[str, Any] | None:
        with self._condition:
            status = self._statuses.get(operation_id)
            return dict(status) if status is not None else None

    def run_pending_once(self, *, ignore_delay: bool = False) -> bool:
        with self._condition:
            if not self._tasks:
                return False

            task = self._tasks[0]

            if not ignore_delay and task.next_attempt_at > time.monotonic():
                return False

            self._tasks.popleft()

        try:
            task.callback()

        except sqlite3.Error as error:
            task.attempts += 1

            if task.attempts < self.max_retries:
                task.next_attempt_at = (
                    time.monotonic() + self.retry_delay_seconds
                )

                with self._condition:
                    self._statuses[task.operation_id]["attempts"] = (
                        task.attempts
                    )
                    # Preserve save order so a later Assistant row cannot be
                    # retried ahead of its user row.
                    self._tasks.appendleft(task)
                    self._condition.notify_all()

                return True

            self._mark_failed(task, error)
            return True

        except Exception as error:
            task.attempts += 1
            self._mark_failed(task, error)
            return True

        with self._condition:
            self._statuses[task.operation_id] = {
                "operation_id": task.operation_id,
                "status": "succeeded",
                "attempts": task.attempts + 1,
                "max_retries": self.max_retries,
            }
            self._complete_scope_locked(task.scope_id)
            self._prune_terminal_statuses_locked()
            self._condition.notify_all()

        return True

    def close(self, *, wait: bool = False) -> None:
        with self._condition:
            self._stopped = True
            worker = self._worker
            self._condition.notify_all()

        if wait and worker is not None:
            worker.join(timeout=2.0)

    def _start_worker_locked(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return

        self._stopped = False
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="conversation-persistence-retry",
            daemon=True,
        )
        self._worker.start()

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while not self._tasks and not self._stopped:
                    self._condition.wait()

                if self._stopped:
                    return

                delay = self._tasks[0].next_attempt_at - time.monotonic()

                if delay > 0:
                    self._condition.wait(timeout=delay)
                    continue

            self.run_pending_once()

    def _mark_failed(self, task: _RetryTask, error: Exception) -> None:
        with self._condition:
            self._statuses[task.operation_id] = {
                "operation_id": task.operation_id,
                "status": "failed",
                "attempts": task.attempts,
                "max_retries": self.max_retries,
            }
            self._complete_scope_locked(task.scope_id)
            self._prune_terminal_statuses_locked()
            self._condition.notify_all()

        logger.error(
            "Conversation history persistence failed permanently: "
            "operation_id=%s attempts=%s",
            task.operation_id,
            task.attempts,
            exc_info=(type(error), error, error.__traceback__),
        )

    def _complete_scope_locked(self, scope_id: str) -> None:
        remaining = self._pending_scope_counts.get(scope_id, 0) - 1

        if remaining > 0:
            self._pending_scope_counts[scope_id] = remaining
        else:
            self._pending_scope_counts.pop(scope_id, None)

    def _prune_terminal_statuses_locked(self) -> None:
        while len(self._statuses) > CONVERSATION_PERSISTENCE_STATUS_LIMIT:
            terminal_operation_id = next(
                (
                    operation_id
                    for operation_id, status in self._statuses.items()
                    if status["status"] != "pending"
                ),
                None,
            )

            if terminal_operation_id is None:
                return

            self._statuses.pop(terminal_operation_id, None)


_default_retry_queue = ConversationPersistenceRetryQueue()


def get_conversation_persistence_retry_queue(
) -> ConversationPersistenceRetryQueue:
    return _default_retry_queue


def persist_conversation_message(
    *,
    operation: Callable[[str], dict[str, Any]],
    conversation_id: str,
    role: str,
    content: str,
    source: str,
    status: str,
    identity_key: str | None = None,
    retry_queue: ConversationPersistenceRetryQueue | None = None,
) -> ConversationPersistenceOutcome:
    """Persist now, or return an accepted placeholder and retry in memory."""

    message_id = (
        uuid5(CONVERSATION_MESSAGE_NAMESPACE, identity_key).hex
        if identity_key
        else uuid4().hex
    )
    queue = retry_queue or get_conversation_persistence_retry_queue()

    def retry_callback() -> dict[str, Any]:
        return operation(message_id)

    if queue.has_pending(conversation_id):
        queue.enqueue(
            message_id,
            retry_callback,
            scope_id=conversation_id,
        )
        return _pending_persistence_outcome(
            message_id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            source=source,
            status=status,
        )

    try:
        message = operation(message_id)
        return ConversationPersistenceOutcome(message=message)

    except sqlite3.Error:
        queue.enqueue(
            message_id,
            retry_callback,
            scope_id=conversation_id,
        )


    return _pending_persistence_outcome(
        message_id=message_id,
        conversation_id=conversation_id,
        role=role,
        content=content,
        source=source,
        status=status,
    )


def _pending_persistence_outcome(
    *,
    message_id: str,
    conversation_id: str,
    role: str,
    content: str,
    source: str,
    status: str,
) -> ConversationPersistenceOutcome:
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return ConversationPersistenceOutcome(
        message={
            "id": message_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "source": source,
            "status": status,
            "created_at": now,
            "updated_at": now,
        },
        operation_id=message_id,
    )
