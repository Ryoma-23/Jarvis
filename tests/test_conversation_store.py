import sqlite3
import tempfile
import unittest

from contextlib import closing
from pathlib import Path

from app.services.conversation_store import (
    ConversationNotFoundError,
    ConversationStore,
    DuplicateMessageError,
    MessageNotFoundError,
)


class ConversationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_directory.name) / "conversations.sqlite3"
        self.store = ConversationStore(self.db_path)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_schema_contains_conversations_messages_and_unique_indexes(self):
        with closing(sqlite3.connect(self.db_path)) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
            user_version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

        self.assertIn("conversations", tables)
        self.assertIn("messages", tables)
        self.assertIn("idx_conversations_single_active", indexes)
        self.assertIn("idx_messages_item_id", indexes)
        self.assertIn("idx_messages_response_id", indexes)
        self.assertEqual(user_version, 1)

    def test_get_or_create_active_conversation_reuses_one_conversation(self):
        first = self.store.get_or_create_active_conversation(title="JARVIS")
        second = self.store.get_or_create_active_conversation(title="ignored")

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["title"], "JARVIS")
        self.assertTrue(second["is_active"])

    def test_active_conversation_and_messages_survive_store_reopen(self):
        conversation = self.store.create_conversation(make_active=True)
        message = self.store.add_message(
            conversation["id"],
            role="user",
            content="永続化するメッセージ",
            source="text",
        )

        reopened_store = ConversationStore(self.db_path)

        self.assertEqual(
            reopened_store.get_active_conversation()["id"],
            conversation["id"],
        )
        self.assertEqual(
            reopened_store.get_messages(conversation["id"])[0]["id"],
            message["id"],
        )

    def test_active_conversation_can_be_switched_and_cleared(self):
        first = self.store.create_conversation(make_active=True)
        second = self.store.create_conversation()

        active = self.store.set_active_conversation(second["id"])

        self.assertEqual(active["id"], second["id"])
        self.assertFalse(
            self.store.get_conversation(first["id"])["is_active"]
        )

        self.store.clear_active_conversation()
        self.assertIsNone(self.store.get_active_conversation())

        with self.assertRaises(ConversationNotFoundError):
            self.store.set_active_conversation("missing")

    def test_messages_are_stored_and_returned_in_conversation_order(self):
        conversation = self.store.create_conversation(make_active=True)
        user_message = self.store.add_message(
            conversation["id"],
            role="user",
            content="こんにちは",
            source="text",
            item_id="item-user-1",
            metadata={"language": "ja"},
        )
        assistant_message = self.store.add_message(
            conversation["id"],
            role="assistant",
            content="こんにちは。",
            source="voice",
            status="pending",
            item_id="item-assistant-1",
            response_id="response-1",
        )

        messages = self.store.get_messages(conversation["id"])

        self.assertEqual(
            [message["id"] for message in messages],
            [user_message["id"], assistant_message["id"]],
        )
        self.assertEqual(messages[0]["metadata"], {"language": "ja"})
        self.assertEqual(messages[1]["status"], "pending")
        self.assertEqual(
            self.store.get_message(assistant_message["id"])["response_id"],
            "response-1",
        )
        self.assertEqual(
            self.store.get_message_by_item_id("item-assistant-1")["id"],
            assistant_message["id"],
        )
        self.assertEqual(
            self.store.get_message_by_response_id("response-1")["id"],
            assistant_message["id"],
        )
        self.assertIsNone(self.store.get_message_by_item_id("missing"))

    def test_message_limit_returns_most_recent_messages_in_order(self):
        conversation = self.store.create_conversation()

        for index in range(4):
            self.store.add_message(
                conversation["id"],
                role="user",
                content=f"message-{index}",
                source="text",
            )

        messages = self.store.get_messages(conversation["id"], limit=2)

        self.assertEqual(
            [message["content"] for message in messages],
            ["message-2", "message-3"],
        )

        with self.assertRaises(ValueError):
            self.store.get_messages(conversation["id"], limit=0)

    def test_item_id_and_response_id_make_message_add_idempotent(self):
        conversation = self.store.create_conversation()
        original = self.store.add_message(
            conversation["id"],
            role="assistant",
            content="回答",
            source="voice",
            item_id="item-1",
            response_id="response-1",
        )

        item_retry = self.store.add_message(
            conversation["id"],
            role="assistant",
            content="回答",
            source="voice",
            item_id="item-1",
        )
        response_retry = self.store.add_message(
            conversation["id"],
            role="assistant",
            content="回答",
            source="voice",
            response_id="response-1",
        )

        self.assertEqual(item_retry["id"], original["id"])
        self.assertEqual(response_retry["id"], original["id"])
        self.assertEqual(len(self.store.get_messages(conversation["id"])), 1)

    def test_retry_can_fill_the_other_external_id(self):
        conversation = self.store.create_conversation()
        original = self.store.add_message(
            conversation["id"],
            role="assistant",
            content="回答",
            source="voice",
            item_id="item-1",
        )

        retry = self.store.add_message(
            conversation["id"],
            role="assistant",
            content="回答",
            source="voice",
            item_id="item-1",
            response_id="response-1",
        )

        self.assertEqual(retry["id"], original["id"])
        self.assertEqual(retry["response_id"], "response-1")
        self.assertEqual(len(self.store.get_messages(conversation["id"])), 1)

    def test_conflicting_external_ids_are_rejected(self):
        conversation = self.store.create_conversation()
        self.store.add_message(
            conversation["id"],
            role="assistant",
            content="first",
            source="voice",
            item_id="item-1",
        )
        self.store.add_message(
            conversation["id"],
            role="assistant",
            content="second",
            source="voice",
            item_id="item-2",
            response_id="response-2",
        )

        with self.assertRaises(DuplicateMessageError):
            self.store.add_message(
                conversation["id"],
                role="assistant",
                content="conflict",
                source="voice",
                item_id="item-1",
                response_id="response-2",
            )

        with self.assertRaises(DuplicateMessageError):
            self.store.add_message(
                conversation["id"],
                role="assistant",
                content="conflict",
                source="voice",
                item_id="different-item",
                response_id="response-2",
            )

    def test_message_status_can_be_interrupted_or_failed(self):
        conversation = self.store.create_conversation()
        message = self.store.add_message(
            conversation["id"],
            role="assistant",
            content="",
            source="voice",
            status="pending",
        )

        interrupted = self.store.update_message_status(
            message["id"],
            "interrupted",
            content="途中までの回答",
        )
        failed = self.store.update_message_status(
            message["id"],
            "failed",
            error_message="connection closed",
        )

        self.assertEqual(interrupted["content"], "途中までの回答")
        self.assertEqual(interrupted["status"], "interrupted")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error_message"], "connection closed")

        with self.assertRaises(ValueError):
            self.store.update_message_status(message["id"], "unknown")

        with self.assertRaises(MessageNotFoundError):
            self.store.update_message_status("missing", "failed")

    def test_explicit_transaction_rolls_back_all_writes_on_error(self):
        conversation_id = "rolled-back-conversation"

        with self.assertRaises(RuntimeError):
            with self.store.transaction() as connection:
                self.store.create_conversation(
                    conversation_id=conversation_id,
                    make_active=True,
                    connection=connection,
                )
                self.store.add_message(
                    conversation_id,
                    role="user",
                    content="保存されない",
                    source="text",
                    connection=connection,
                )
                raise RuntimeError("rollback")

        self.assertIsNone(self.store.get_conversation(conversation_id))
        self.assertIsNone(self.store.get_active_conversation())

    def test_invalid_message_and_unknown_conversation_are_rejected(self):
        conversation = self.store.create_conversation()

        with self.assertRaises(ValueError):
            self.store.add_message(
                conversation["id"],
                role="invalid",
                content="message",
                source="text",
            )

        with self.assertRaises(ConversationNotFoundError):
            self.store.add_message(
                "missing",
                role="user",
                content="message",
                source="text",
            )

        with self.assertRaises(ConversationNotFoundError):
            self.store.get_messages("missing")


if __name__ == "__main__":
    unittest.main()
