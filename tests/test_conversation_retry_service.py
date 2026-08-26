import sqlite3
import tempfile
import threading
import time
import unittest

from pathlib import Path
from unittest.mock import patch

from app.services.conversation_retry_service import (
    ConversationPersistenceRetryQueue,
    persist_conversation_message,
)
from app.services.conversation_store import (
    ConversationStore,
    DuplicateMessageError,
)


class ConversationPersistenceRetryQueueTests(unittest.TestCase):
    def test_daemon_worker_processes_retry_without_blocking_caller(self):
        queue = ConversationPersistenceRetryQueue(
            max_retries=3,
            retry_delay_seconds=0,
            auto_start=True,
        )
        completed = threading.Event()

        def operation():
            completed.set()
            return {"saved": True}

        try:
            self.assertTrue(
                queue.enqueue(
                    "daemon-operation",
                    operation,
                    scope_id="conversation-1",
                )
            )
            self.assertTrue(completed.wait(timeout=1.0))
            deadline = time.monotonic() + 1.0

            while (
                queue.get_status("daemon-operation")["status"] != "succeeded"
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)

            self.assertEqual(
                queue.get_status("daemon-operation")["status"],
                "succeeded",
            )
        finally:
            queue.close(wait=True)

    def test_sqlite_failure_is_retried_until_success(self):
        queue = ConversationPersistenceRetryQueue(
            max_retries=3,
            retry_delay_seconds=0,
            auto_start=False,
        )
        calls = []

        def operation():
            calls.append("attempt")

            if len(calls) < 3:
                raise sqlite3.OperationalError("database is locked")

            return {"saved": True}

        self.assertTrue(
            queue.enqueue("operation-1", operation, scope_id="conversation-1")
        )
        self.assertFalse(
            queue.enqueue("operation-1", operation, scope_id="conversation-1")
        )

        for _ in range(3):
            self.assertTrue(queue.run_pending_once(ignore_delay=True))

        self.assertEqual(len(calls), 3)
        self.assertEqual(queue.get_status("operation-1")["status"], "succeeded")
        self.assertEqual(queue.get_status("operation-1")["attempts"], 3)
        self.assertFalse(queue.has_pending("conversation-1"))

    def test_only_final_failure_is_logged(self):
        queue = ConversationPersistenceRetryQueue(
            max_retries=3,
            retry_delay_seconds=0,
            auto_start=False,
        )

        def operation():
            raise sqlite3.OperationalError("disk I/O error")

        with patch(
            "app.services.conversation_retry_service.logger.error"
        ) as log_error:
            queue.enqueue(
                "operation-final-failure",
                operation,
                scope_id="conversation-1",
            )

            self.assertTrue(queue.run_pending_once(ignore_delay=True))
            self.assertTrue(queue.run_pending_once(ignore_delay=True))
            log_error.assert_not_called()

            self.assertTrue(queue.run_pending_once(ignore_delay=True))
            log_error.assert_called_once()

        status = queue.get_status("operation-final-failure")
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["attempts"], 3)

    def test_later_message_waits_behind_failed_write_for_same_conversation(self):
        queue = ConversationPersistenceRetryQueue(
            max_retries=3,
            retry_delay_seconds=0,
            auto_start=False,
        )
        saved_roles = []
        user_calls = 0

        def save_user(message_id):
            nonlocal user_calls
            user_calls += 1

            if user_calls == 1:
                raise sqlite3.OperationalError("database is locked")

            saved_roles.append(("user", message_id))
            return {"id": message_id}

        def save_assistant(message_id):
            saved_roles.append(("assistant", message_id))
            return {"id": message_id}

        user_outcome = persist_conversation_message(
            operation=save_user,
            conversation_id="conversation-1",
            role="user",
            content="質問",
            source="text",
            status="completed",
            retry_queue=queue,
        )
        assistant_outcome = persist_conversation_message(
            operation=save_assistant,
            conversation_id="conversation-1",
            role="assistant",
            content="回答",
            source="text",
            status="completed",
            retry_queue=queue,
        )

        self.assertTrue(user_outcome.pending)
        self.assertTrue(assistant_outcome.pending)
        self.assertEqual(saved_roles, [])

        queue.run_pending_once(ignore_delay=True)
        queue.run_pending_once(ignore_delay=True)

        self.assertEqual(
            [role for role, _ in saved_roles],
            ["user", "assistant"],
        )

    def test_identity_key_deduplicates_pending_operation(self):
        queue = ConversationPersistenceRetryQueue(
            max_retries=3,
            retry_delay_seconds=0,
            auto_start=False,
        )
        calls = 0

        def operation(message_id):
            nonlocal calls
            calls += 1

            if calls == 1:
                raise sqlite3.OperationalError("database is locked")

            return {"id": message_id}

        first = persist_conversation_message(
            operation=operation,
            conversation_id="conversation-1",
            role="user",
            content="同じイベント",
            source="voice",
            status="completed",
            identity_key="realtime-user:item-1",
            retry_queue=queue,
        )
        duplicate = persist_conversation_message(
            operation=operation,
            conversation_id="conversation-1",
            role="user",
            content="同じイベント",
            source="voice",
            status="completed",
            identity_key="realtime-user:item-1",
            retry_queue=queue,
        )

        self.assertEqual(first.message["id"], duplicate.message["id"])
        queue.run_pending_once(ignore_delay=True)
        self.assertEqual(calls, 2)
        self.assertEqual(
            queue.get_status(first.operation_id)["status"],
            "succeeded",
        )


class ConversationStoreMessageIdRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_directory.name) / "conversations.sqlite3"
        self.store = ConversationStore(db_path)
        self.conversation = self.store.create_conversation(make_active=True)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_message_id_retry_does_not_duplicate_row(self):
        first = self.store.add_message(
            self.conversation["id"],
            role="user",
            content="一度だけ保存",
            source="text",
            message_id="stable-message-id",
        )
        retry = self.store.add_message(
            self.conversation["id"],
            role="user",
            content="一度だけ保存",
            source="text",
            message_id="stable-message-id",
        )

        self.assertEqual(retry["id"], first["id"])
        self.assertEqual(
            len(self.store.get_messages(self.conversation["id"])),
            1,
        )

        with self.assertRaises(DuplicateMessageError):
            self.store.add_message(
                self.conversation["id"],
                role="user",
                content="異なる内容",
                source="text",
                message_id="stable-message-id",
            )


if __name__ == "__main__":
    unittest.main()
