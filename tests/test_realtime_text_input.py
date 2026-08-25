import unittest
from pathlib import Path


class RealtimeTextInputFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = Path("static/script.js").read_text(encoding="utf-8")

    def test_send_path_switches_to_realtime_only_while_lifecycle_is_active(self):
        send_start = self.script.index("async function sendMessage")
        send_end = self.script.index("function shouldUseRealtimeTextInput")
        send_source = self.script[send_start:send_end]

        self.assertIn("if (shouldUseRealtimeTextInput())", send_source)
        self.assertIn("enqueueRealtimeTextInput(message)", send_source)
        self.assertIn("await sendHttpChatMessage(message)", send_source)

        realtime_start = self.script.index("function enqueueRealtimeTextInput")
        realtime_end = self.script.index("function requestRealtimeVoiceStart")
        realtime_source = self.script[realtime_start:realtime_end]
        self.assertNotIn('fetch("/chat/stream"', realtime_source)

        http_start = self.script.index("async function sendHttpChatMessage")
        http_end = self.script.index("function shouldUseRealtimeTextInput")
        self.assertIn(
            'fetch("/chat/stream"',
            self.script[http_start:http_end],
        )

    def test_realtime_text_is_saved_before_response_create(self):
        process_start = self.script.index(
            "function processRealtimeTextInputQueue"
        )
        added_start = self.script.index(
            "async function handleRealtimeTextInputItemAdded"
        )
        done_start = self.script.index(
            "async function handleRealtimeTextInputItemDone"
        )
        reject_start = self.script.index(
            "function rejectRealtimeTextTurnFromServer"
        )

        process_source = self.script[process_start:added_start]
        added_source = self.script[added_start:done_start]
        done_source = self.script[done_start:reject_start]

        self.assertIn('type: "conversation.item.create"', process_source)
        self.assertIn('type: "input_text"', process_source)
        self.assertNotIn('type: "response.create"', process_source)
        self.assertIn("saveRealtimeConversationMessage({", added_source)
        self.assertIn('source: "text"', added_source)
        self.assertIn("await turn.userPersistPromise", done_source)
        self.assertIn(
            "requestRealtimeResponse(sessionId, turn)",
            done_source,
        )

    def test_realtime_audio_transcript_keeps_text_turn_source(self):
        state_start = self.script.index(
            "function getRealtimeAssistantTranscriptState"
        )
        state_end = self.script.index(
            "function markActiveRealtimeAssistantInterrupted"
        )
        state_source = self.script[state_start:state_end]

        self.assertIn("realtimeTextTurnsByResponseId.has(responseId)", state_source)
        self.assertIn('? "text"', state_source)
        self.assertIn("state.source = \"text\"", state_source)

        done_start = self.script.index(
            "async function handleRealtimeAssistantTranscriptDone"
        )
        done_end = self.script.index(
            "function getRealtimeAssistantTranscriptState"
        )
        done_source = self.script[done_start:done_end]
        self.assertIn("source: state.source", done_source)
        self.assertIn("saveRealtimeConversationMessage({", done_source)

    def test_text_requests_are_queued_and_tool_followups_keep_the_turn(self):
        process_start = self.script.index(
            "function processRealtimeTextInputQueue"
        )
        process_end = self.script.index(
            "async function handleRealtimeTextInputItemAdded"
        )
        process_source = self.script[process_start:process_end]

        self.assertIn("activeRealtimeTextTurn", process_source)
        self.assertIn("realtimeTextInputQueue.length === 0", process_source)
        self.assertIn("isRealtimeUserSpeechActive", process_source)
        self.assertIn("isRealtimeResponseCancelPending", process_source)
        interrupt_index = process_source.index(
            "interruptRealtimeResponse(lifecycle.sessionId)"
        )
        self.assertIn("return;", process_source[interrupt_index:])

        response_done_start = self.script.index(
            'if (data.type === "response.done")'
        )
        response_done_end = self.script.index(
            "function realtimeResponseHasFunctionCall"
        )
        self.assertIn(
            "isRealtimeResponseCancelPending = false",
            self.script[response_done_start:response_done_end],
        )
        self.assertIn(
            'hasFunctionCall && responseStatus === "completed"',
            self.script[response_done_start:response_done_end],
        )

        tool_start = self.script.index("async function handleRealtimeToolCall")
        tool_end = self.script.index("function renderConversationHistory")
        tool_source = self.script[tool_start:tool_end]
        self.assertIn('type: "function_call_output"', tool_source)
        self.assertIn("realtimeTextTurnsByResponseId.get(responseId)", tool_source)
        self.assertIn("requestRealtimeResponse(sessionId, textTurn)", tool_source)


if __name__ == "__main__":
    unittest.main()
