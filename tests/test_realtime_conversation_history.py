import tempfile
import unittest

from pathlib import Path

from app.services.conversation_service import ConversationService
from app.services.conversation_store import ConversationStore


class RealtimeConversationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_directory.name) / "conversations.sqlite3"
        self.service = ConversationService(ConversationStore(db_path))

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_voice_transcripts_are_saved_once_by_external_ids(self):
        user = self.service.record_realtime_user_transcript(
            "音声の質問",
            item_id="user-item-1",
        )
        user_retry = self.service.record_realtime_user_transcript(
            "音声の質問",
            item_id="user-item-1",
        )
        assistant = self.service.record_realtime_assistant_transcript(
            "音声の回答",
            item_id="assistant-item-1",
            response_id="response-1",
        )
        assistant_retry = self.service.record_realtime_assistant_transcript(
            "音声の回答",
            item_id="assistant-item-1",
            response_id="response-1",
        )

        conversation = self.service.get_active_conversation()
        messages = self.service.store.get_messages(conversation["id"])

        self.assertEqual(user_retry["id"], user["id"])
        self.assertEqual(assistant_retry["id"], assistant["id"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(
            [(message["role"], message["source"]) for message in messages],
            [("user", "voice"), ("assistant", "voice")],
        )

    def test_realtime_text_turn_is_saved_once_with_text_source(self):
        user = self.service.record_realtime_user_message(
            "画面からの質問",
            source="text",
            item_id="text-user-item-1",
        )
        user_retry = self.service.record_realtime_user_message(
            "画面からの質問",
            source="text",
            item_id="text-user-item-1",
        )
        assistant = self.service.record_realtime_assistant_message(
            "音声でも再生される回答",
            source="text",
            item_id="text-assistant-item-1",
            response_id="text-response-1",
        )
        assistant_retry = self.service.record_realtime_assistant_message(
            "音声でも再生される回答",
            source="text",
            item_id="text-assistant-item-1",
            response_id="text-response-1",
        )

        conversation = self.service.get_active_conversation()
        messages = self.service.store.get_messages(conversation["id"])

        self.assertEqual(user_retry["id"], user["id"])
        self.assertEqual(assistant_retry["id"], assistant["id"])
        self.assertEqual(
            [(message["role"], message["source"]) for message in messages],
            [("user", "text"), ("assistant", "text")],
        )

    def test_realtime_text_assistant_can_be_marked_interrupted(self):
        completed = self.service.record_realtime_assistant_message(
            "テキスト起点の回答",
            source="text",
            item_id="text-assistant-interrupted",
            response_id="text-response-interrupted",
        )
        interrupted = self.service.interrupt_realtime_assistant_message(
            content="テキスト起点の回答",
            source="text",
            item_id="text-assistant-interrupted",
            response_id="text-response-interrupted",
        )

        self.assertEqual(interrupted["id"], completed["id"])
        self.assertEqual(interrupted["source"], "text")
        self.assertEqual(interrupted["status"], "interrupted")

    def test_interruption_before_done_keeps_partial_transcript_interrupted(self):
        interrupted = self.service.interrupt_realtime_assistant_message(
            content="回答の途中",
            response_id="response-before-done",
        )
        finalized = self.service.record_realtime_assistant_transcript(
            "回答の途中ですが続きも生成済み",
            item_id="assistant-before-done",
            response_id="response-before-done",
        )

        self.assertEqual(finalized["id"], interrupted["id"])
        self.assertEqual(finalized["status"], "interrupted")
        self.assertEqual(finalized["content"], "回答の途中")
        self.assertEqual(finalized["item_id"], "assistant-before-done")

    def test_done_after_empty_interruption_fills_transcript_without_completing(self):
        interrupted = self.service.interrupt_realtime_assistant_message(
            response_id="response-empty-interruption",
        )
        finalized = self.service.record_realtime_assistant_transcript(
            "確定時に取得できた音声回答",
            item_id="assistant-empty-interruption",
            response_id="response-empty-interruption",
        )

        self.assertEqual(finalized["id"], interrupted["id"])
        self.assertEqual(finalized["status"], "interrupted")
        self.assertEqual(finalized["content"], "確定時に取得できた音声回答")

    def test_interruption_after_done_changes_completed_message_status(self):
        completed = self.service.record_realtime_assistant_transcript(
            "最後まで生成された回答",
            item_id="assistant-after-done",
            response_id="response-after-done",
        )
        interrupted = self.service.interrupt_realtime_assistant_message(
            content="実際に表示した途中まで",
            item_id="assistant-after-done",
            response_id="response-after-done",
        )

        self.assertEqual(interrupted["id"], completed["id"])
        self.assertEqual(interrupted["status"], "interrupted")
        self.assertEqual(interrupted["content"], "実際に表示した途中まで")
        self.assertEqual(self.service.build_context(), [])


class RealtimeConversationEventContractTests(unittest.TestCase):
    def test_realtime_events_use_delta_for_display_and_done_for_persistence(self):
        script = Path("static/script.js").read_text(encoding="utf-8")

        for event_type in (
            "conversation.item.input_audio_transcription.completed",
            "response.output_audio_transcript.delta",
            "response.output_audio_transcript.done",
        ):
            self.assertIn(event_type, script)

        delta_start = script.index(
            "function handleRealtimeAssistantTranscriptDelta"
        )
        done_start = script.index(
            "async function handleRealtimeAssistantTranscriptDone"
        )
        delta_source = script[delta_start:done_start]
        done_source = script[done_start:]

        self.assertNotIn("saveRealtimeConversationMessage", delta_source)
        self.assertIn("saveRealtimeConversationMessage", done_source)
        self.assertIn("appendMessageText", delta_source)
        self.assertIn("markActiveRealtimeAssistantInterrupted", script)

    def test_user_transcript_controls_display_and_manual_response(self):
        script = Path("static/script.js").read_text(encoding="utf-8")

        handler_start = script.index(
            "async function handleRealtimeUserTranscriptionCompleted"
        )
        handler_end = script.index(
            "function handleRealtimeAssistantTranscriptDelta"
        )
        handler_source = script[handler_start:handler_end]

        self.assertIn("create_response: false", script)
        self.assertIn(
            "isMeaningfulRealtimeUserTranscript(transcript, isBargeIn)",
            handler_source,
        )
        self.assertIn(
            "(isBargeIn && !passedBargeInGuard)",
            handler_source,
        )
        self.assertIn(
            "interruptRealtimeResponse(sessionId)",
            handler_source,
        )
        self.assertIn(
            "requestRealtimeResponse(sessionId)",
            handler_source,
        )
        self.assertIn(
            "renderConversationMessage({",
            handler_source,
        )
        self.assertIn(
            "saveRealtimeConversationMessage({",
            handler_source,
        )
        self.assertIn(
            "conversation.item.input_audio_transcription.failed",
            script,
        )

    def test_realtime_routes_expose_save_and_interrupt_operations(self):
        route = Path("app/routes/realtime.py").read_text(encoding="utf-8")

        self.assertIn(
            '@router.post("/realtime/conversation/messages")',
            route,
        )
        self.assertIn(
            '@router.post("/realtime/conversation/assistant/interrupted")',
            route,
        )
        self.assertIn('source: Literal["text", "voice"] = "voice"', route)
        self.assertIn("record_realtime_user_message", route)
        self.assertIn("record_realtime_assistant_message", route)
        self.assertIn("interrupt_realtime_assistant_message", route)


if __name__ == "__main__":
    unittest.main()
