import tempfile
import unittest

from pathlib import Path

from app.services.conversation_service import ConversationService
from app.services.conversation_store import ConversationStore


class ConversationServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_directory.name) / "conversations.sqlite3"
        self.store = ConversationStore(db_path)
        self.service = ConversationService(self.store)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_active_conversation_can_be_created_reused_and_replaced(self):
        self.assertIsNone(self.service.get_active_conversation())

        first = self.service.get_or_create_active_conversation(title="first")
        reused = self.service.get_or_create_active_conversation(title="ignored")
        second = self.service.create_active_conversation(title="second")

        self.assertEqual(reused["id"], first["id"])
        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(
            self.service.get_active_conversation()["id"],
            second["id"],
        )

    def test_adding_a_message_creates_an_active_conversation_atomically(self):
        message = self.service.add_user_message(
            "最初のメッセージ",
            source="text",
        )

        active = self.service.get_active_conversation()

        self.assertIsNotNone(active)
        self.assertEqual(message["conversation_id"], active["id"])
        self.assertEqual(len(self.store.get_messages(active["id"])), 1)

    def test_user_and_assistant_messages_preserve_text_and_voice_sources(self):
        user_message = self.service.add_user_message(
            "テキスト入力",
            source="text",
            item_id="user-item",
        )
        assistant_message = self.service.add_assistant_message(
            "音声回答",
            source="voice",
            item_id="assistant-item",
            response_id="response-1",
        )

        self.assertEqual(user_message["role"], "user")
        self.assertEqual(user_message["source"], "text")
        self.assertEqual(assistant_message["role"], "assistant")
        self.assertEqual(assistant_message["source"], "voice")

        with self.assertRaises(ValueError):
            self.service.add_user_message("invalid", source="tool")

        with self.assertRaises(ValueError):
            self.service.add_assistant_message("", source="text")

    def test_context_contains_the_most_recent_fifteen_turns(self):
        for index in range(17):
            source = "text" if index % 2 == 0 else "voice"
            self.service.add_user_message(f"user-{index}", source=source)
            self.service.add_assistant_message(
                f"assistant-{index}",
                source=source,
            )

        context = self.service.build_context()

        self.assertEqual(len(context), 30)
        self.assertEqual(
            context[0],
            {"role": "user", "content": "user-2"},
        )
        self.assertEqual(
            context[-1],
            {"role": "assistant", "content": "assistant-16"},
        )

    def test_context_excludes_interrupted_pending_failed_and_hidden_messages(self):
        self.service.add_user_message("質問1", source="voice")
        self.service.add_assistant_message(
            "途中の回答",
            source="voice",
            status="interrupted",
        )
        self.service.add_user_message("質問2", source="text")
        self.service.add_assistant_message(
            "未完成",
            source="text",
            status="pending",
        )
        self.service.add_assistant_message(
            "失敗",
            source="text",
            status="failed",
            error_message="generation failed",
        )
        self.service.add_assistant_message("回答2", source="text")
        self.service.record_hidden_tool_metadata(
            tool_name="add_note",
            call_id="call-1",
            arguments={"content": "秘密"},
            result={"success": True},
        )

        self.assertEqual(
            self.service.build_context(),
            [
                {"role": "user", "content": "質問1"},
                {"role": "user", "content": "質問2"},
                {"role": "assistant", "content": "回答2"},
            ],
        )

    def test_assistant_message_can_transition_to_interrupted(self):
        self.service.add_user_message("説明して", source="voice")
        pending = self.service.add_assistant_message(
            "",
            source="voice",
            status="pending",
        )

        interrupted = self.service.update_assistant_message(
            pending["id"],
            "interrupted",
            content="説明の途中",
        )

        self.assertEqual(interrupted["status"], "interrupted")
        self.assertEqual(interrupted["content"], "説明の途中")
        self.assertEqual(
            self.service.build_context(),
            [{"role": "user", "content": "説明して"}],
        )

        with self.assertRaises(ValueError):
            self.service.update_assistant_message("missing", "failed")

    def test_hidden_tool_metadata_is_stored_but_not_added_to_context(self):
        self.service.add_user_message("メモして", source="voice")
        hidden = self.service.record_hidden_tool_metadata(
            tool_name="add_note",
            call_id="call-1",
            arguments={"content": "牛乳を買う"},
            result={"success": True, "id": 1},
            item_id="tool-item-1",
        )
        retry = self.service.record_hidden_tool_metadata(
            tool_name="add_note",
            call_id="call-1",
            arguments={"content": "牛乳を買う"},
            result={"success": True, "id": 1},
            item_id="tool-item-1",
        )

        metadata = self.service.get_hidden_tool_metadata()

        self.assertEqual(hidden["id"], retry["id"])
        self.assertEqual(len(metadata), 1)
        self.assertEqual(metadata[0]["role"], "tool")
        self.assertEqual(metadata[0]["source"], "tool")
        self.assertTrue(metadata[0]["metadata"]["hidden"])
        self.assertEqual(
            metadata[0]["metadata"]["tool"],
            {
                "name": "add_note",
                "call_id": "call-1",
                "arguments": {"content": "牛乳を買う"},
                "result": {"success": True, "id": 1},
            },
        )
        self.assertEqual(
            self.service.build_context(),
            [{"role": "user", "content": "メモして"}],
        )

    def test_display_messages_return_safe_text_and_voice_chat_fields(self):
        text_user = self.service.add_user_message(
            "<script>alert('unsafe')</script>",
            source="text",
        )
        failed_assistant = self.service.add_assistant_message(
            "途中のテキスト回答",
            source="text",
            status="failed",
            error_message="internal error",
            metadata={"private": "not-for-ui"},
        )
        voice_user = self.service.add_user_message(
            "音声入力",
            source="voice",
        )
        voice_assistant = self.service.add_assistant_message(
            "音声回答",
            source="voice",
        )
        self.service.record_hidden_tool_metadata(
            tool_name="list_notes",
            call_id="display-call",
            arguments={},
            result={"secret": True},
        )

        messages = self.service.get_display_messages()

        self.assertEqual(
            messages,
            [
                {
                    "id": text_user["id"],
                    "conversation_id": text_user["conversation_id"],
                    "role": "user",
                    "content": "<script>alert('unsafe')</script>",
                    "source": "text",
                    "status": "completed",
                    "created_at": text_user["created_at"],
                    "updated_at": text_user["updated_at"],
                },
                {
                    "id": failed_assistant["id"],
                    "conversation_id": failed_assistant["conversation_id"],
                    "role": "assistant",
                    "content": "途中のテキスト回答",
                    "source": "text",
                    "status": "failed",
                    "created_at": failed_assistant["created_at"],
                    "updated_at": failed_assistant["updated_at"],
                },
                {
                    "id": voice_user["id"],
                    "conversation_id": voice_user["conversation_id"],
                    "role": "user",
                    "content": "音声入力",
                    "source": "voice",
                    "status": "completed",
                    "created_at": voice_user["created_at"],
                    "updated_at": voice_user["updated_at"],
                },
                {
                    "id": voice_assistant["id"],
                    "conversation_id": voice_assistant["conversation_id"],
                    "role": "assistant",
                    "content": "音声回答",
                    "source": "voice",
                    "status": "completed",
                    "created_at": voice_assistant["created_at"],
                    "updated_at": voice_assistant["updated_at"],
                },
            ],
        )
        self.assertNotIn("metadata", messages[1])
        self.assertNotIn("error_message", messages[1])

    def test_realtime_restore_events_use_text_history_without_hidden_items(self):
        self.service.add_user_message("音声の質問", source="voice")
        self.service.add_assistant_message("音声の回答", source="voice")
        self.service.add_assistant_message(
            "中断された回答",
            source="voice",
            status="interrupted",
        )
        self.service.record_hidden_tool_metadata(
            tool_name="list_notes",
            call_id="call-2",
            arguments={},
            result={"success": True},
        )

        events = self.service.build_realtime_restore_events()

        self.assertEqual(
            events,
            [
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "音声の質問",
                            }
                        ],
                    },
                },
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "音声の回答",
                            }
                        ],
                        "status": "completed",
                    },
                },
            ],
        )

    def test_context_can_target_a_non_active_conversation(self):
        first = self.service.create_active_conversation(title="first")
        self.service.add_user_message("first message", source="text")
        self.service.create_active_conversation(title="second")
        self.service.add_user_message("second message", source="voice")

        self.assertEqual(
            self.service.build_context(conversation_id=first["id"]),
            [{"role": "user", "content": "first message"}],
        )
        self.assertEqual(
            self.service.build_context(),
            [{"role": "user", "content": "second message"}],
        )

        with self.assertRaises(ValueError):
            self.service.build_context(turn_limit=0)


if __name__ == "__main__":
    unittest.main()
