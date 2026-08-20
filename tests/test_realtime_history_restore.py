import unittest
from pathlib import Path


class RealtimeHistoryRouteTests(unittest.TestCase):
    def test_token_and_history_routes_share_conversation_id(self):
        route = Path("app/routes/realtime.py").read_text(encoding="utf-8")
        service = Path("app/services/realtime_service.py").read_text(
            encoding="utf-8"
        )

        for expected in (
            "def get_realtime_token(conversation_id: str | None = None):",
            "conversation_service.get_or_create_active_conversation()",
            "conversation_service.get_conversation(conversation_id)",
            "create_realtime_token(conversation_id=conversation[\"id\"])",
            '@router.get("/realtime/conversation/history")',
            "def get_realtime_conversation_history(conversation_id: str):",
            "build_realtime_restore_events(",
            "turn_limit=DEFAULT_CONTEXT_TURN_LIMIT",
        ):
            self.assertIn(expected, route)

        self.assertIn(
            "def create_realtime_token(*, conversation_id: str):",
            service,
        )
        self.assertIn(
            'token_data["conversation_id"] = conversation_id',
            service,
        )


class RealtimeHistoryFrontendContractTests(unittest.TestCase):
    def test_history_is_restored_before_microphone_is_enabled(self):
        with open("static/script.js", encoding="utf-8") as script_file:
            script = script_file.read()

        for expected in (
            "REALTIME_HISTORY_RESTORE_TIMEOUT_MS = 5000",
            '"/realtime/token?conversation_id="',
            "tokenData.conversation_id",
            "track.enabled = false",
            "initializeRealtimeDataChannel(",
            "await restoreRealtimeConversationHistory(",
            "setRealtimeMicrophoneEnabled(currentLocalStream, true)",
            'data.type === "conversation.item.added"',
            "registerRealtimeHistoryItemAdded(data, sessionId)",
            'data.type === "conversation.item.done"',
            "acknowledgeRealtimeHistoryItemDone(data, sessionId)",
            "expectedItemSignatures: events.map",
            "expectedSignature === itemSignature",
            "realtimeRestoredItemIds.add(itemId)",
            "isRestoredRealtimeItem(data)",
            "rejectRealtimeHistoryRestoreFromServer(data, sessionId)",
            "lifecycle.sessionCreatedReceived = true",
            "if (!lifecycle.historyRestoring)",
            '"history_restore_failed"',
            "cancelRealtimeHistoryRestore(",
        ):
            self.assertIn(expected, script)

        initialize_start = script.index(
            "async function initializeRealtimeDataChannel"
        )
        initialize_end = script.index(
            "async function restoreRealtimeConversationHistory"
        )
        initialize_source = script[initialize_start:initialize_end]
        restore_position = initialize_source.index(
            "await restoreRealtimeConversationHistory("
        )
        microphone_position = initialize_source.index(
            "setRealtimeMicrophoneEnabled(currentLocalStream, true)"
        )
        self.assertLess(restore_position, microphone_position)

        added_start = script.index(
            "function registerRealtimeHistoryItemAdded"
        )
        done_start = script.index(
            "function acknowledgeRealtimeHistoryItemDone"
        )
        sync_start = script.index(
            "function queueRealtimeTextContextSync"
        )
        added_source = script[added_start:done_start]
        done_source = script[done_start:sync_start]

        self.assertNotIn("remainingItemCount -= 1", added_source)
        self.assertIn("remainingItemCount -= 1", done_source)
        self.assertIn("completedItemIds.has(itemId)", done_source)

    def test_restore_sends_only_history_items_in_server_order(self):
        with open("static/script.js", encoding="utf-8") as script_file:
            script = script_file.read()

        restore_start = script.index(
            "async function restoreRealtimeConversationHistory"
        )
        restore_end = script.index(
            "function beginRealtimeHistoryRestore"
        )
        restore_source = script[restore_start:restore_end]

        self.assertIn("events.forEach(function(event, index)", restore_source)
        self.assertIn("event_id: eventId", restore_source)
        self.assertIn(
            "currentDataChannel.send(JSON.stringify(restoreEvent))",
            restore_source,
        )
        self.assertNotIn('type: "response.create"', restore_source)

    def test_completed_text_exchange_is_synced_to_an_open_realtime_session(self):
        with open("static/script.js", encoding="utf-8") as script_file:
            script = script_file.read()

        send_start = script.index("async function sendMessage")
        send_end = script.index("function requestRealtimeVoiceStart")
        send_source = script[send_start:send_end]

        self.assertIn("fullAssistantText += data.text", send_source)
        self.assertIn("await queueRealtimeTextContextSync(", send_source)

        sync_start = script.index(
            "async function syncCompletedTextExchangeToRealtime"
        )
        sync_end = script.index(
            "function completeRealtimeHistoryRestore"
        )
        sync_source = script[sync_start:sync_end]

        user_position = sync_source.index('role: "user"')
        assistant_position = sync_source.index('role: "assistant"')
        self.assertLess(user_position, assistant_position)
        self.assertIn('type: "input_text"', sync_source)
        self.assertIn('type: "output_text"', sync_source)
        self.assertIn(
            "setRealtimeMicrophoneEnabled(currentLocalStream, false)",
            sync_source,
        )
        self.assertIn("await sendRealtimeHistoryItemsAndWait(", sync_source)
        self.assertIn(
            "setRealtimeMicrophoneEnabled(currentLocalStream, true)",
            sync_source,
        )
        self.assertNotIn('type: "response.create"', sync_source)


if __name__ == "__main__":
    unittest.main()
