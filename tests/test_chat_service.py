import json
import sys
import tempfile
import unittest

from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


if "app.openai_client" not in sys.modules:
    openai_client_stub = ModuleType("app.openai_client")
    openai_client_stub.client = Mock()
    openai_client_stub.api_key = "test-api-key"
    sys.modules["app.openai_client"] = openai_client_stub

from app.services import chat_service
from app.services.conversation_service import ConversationService
from app.services.conversation_store import ConversationStore


def parse_sse_payloads(chunks):
    payloads = []

    for chunk in chunks:
        if not chunk.startswith("data: "):
            continue

        payloads.append(json.loads(chunk.removeprefix("data: ").strip()))

    return payloads


def text_delta(text):
    return SimpleNamespace(
        type="response.output_text.delta",
        delta=text,
    )


def response_event(event_type, response_id, error_message=None):
    error = None

    if error_message is not None:
        error = SimpleNamespace(message=error_message)

    return SimpleNamespace(
        type=event_type,
        response=SimpleNamespace(id=response_id, error=error),
    )


class ChatServiceConversationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.db_path = (
            Path(self.temp_directory.name) / "conversations.sqlite3"
        )
        self.service = ConversationService(ConversationStore(self.db_path))
        self.service_patcher = patch.object(
            chat_service,
            "get_conversation_service",
            return_value=self.service,
        )
        self.get_service = self.service_patcher.start()

    def tearDown(self):
        self.service_patcher.stop()
        self.temp_directory.cleanup()

    def test_normal_chat_streams_and_persists_user_and_assistant(self):
        client = Mock()
        client.responses.create.return_value = [
            response_event("response.created", "response-1"),
            text_delta("こんにちは"),
            text_delta("。"),
            response_event("response.completed", "response-1"),
        ]

        with (
            patch.object(chat_service, "client", client),
            patch.object(chat_service, "route_message", return_value="chat"),
            patch.object(
                chat_service,
                "load_system_prompt",
                return_value="system prompt",
            ),
            patch.object(
                chat_service,
                "format_memory_for_prompt",
                return_value="memory context",
            ),
        ):
            chunks = list(chat_service.generate_chat_stream("こんにちは"))

        conversation = self.service.get_active_conversation()
        conversation_id = conversation["id"]
        messages = self.service.store.get_messages(conversation_id)

        self.assertEqual(
            parse_sse_payloads(chunks),
            [
                {
                    "user_message_id": messages[0]["id"],
                    "conversation_id": conversation_id,
                },
                {"text": "こんにちは", "conversation_id": conversation_id},
                {"text": "。", "conversation_id": conversation_id},
                {
                    "done": True,
                    "assistant_message_id": messages[1]["id"],
                    "conversation_id": conversation_id,
                },
            ],
        )
        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [
                ("user", "こんにちは"),
                ("assistant", "こんにちは。"),
            ],
        )
        self.assertEqual(messages[0]["source"], "text")
        self.assertEqual(messages[1]["source"], "text")
        self.assertEqual(messages[1]["status"], "completed")
        self.assertEqual(messages[1]["response_id"], "response-1")
        self.assertFalse(hasattr(chat_service, "conversation_history"))

        request = client.responses.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-5-mini")
        self.assertTrue(request["stream"])
        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertEqual(request["input"][0]["content"], "system prompt")
        self.assertEqual(request["input"][2]["content"], "memory context")
        self.assertEqual(
            request["input"][3:],
            [{"role": "user", "content": "こんにちは"}],
        )

    def test_history_is_reused_after_store_reopen(self):
        first_client = Mock()
        first_client.responses.create.return_value = [text_delta("最初の回答")]

        with (
            patch.object(chat_service, "client", first_client),
            patch.object(chat_service, "route_message", return_value="chat"),
            patch.object(chat_service, "load_system_prompt", return_value="system"),
            patch.object(
                chat_service,
                "format_memory_for_prompt",
                return_value="memory",
            ),
        ):
            first_chunks = list(
                chat_service.generate_chat_stream("最初の質問")
            )

        conversation_id = parse_sse_payloads(first_chunks)[0][
            "conversation_id"
        ]
        reopened_service = ConversationService(
            ConversationStore(self.db_path)
        )
        self.get_service.return_value = reopened_service
        second_client = Mock()
        second_client.responses.create.return_value = [text_delta("次の回答")]

        with (
            patch.object(chat_service, "client", second_client),
            patch.object(chat_service, "route_message", return_value="chat"),
            patch.object(chat_service, "load_system_prompt", return_value="system"),
            patch.object(
                chat_service,
                "format_memory_for_prompt",
                return_value="memory",
            ),
        ):
            second_chunks = list(
                chat_service.generate_chat_stream("次の質問")
            )

        self.assertEqual(
            parse_sse_payloads(second_chunks)[0]["conversation_id"],
            conversation_id,
        )
        self.assertEqual(
            second_client.responses.create.call_args.kwargs["input"][3:],
            [
                {"role": "user", "content": "最初の質問"},
                {"role": "assistant", "content": "最初の回答"},
                {"role": "user", "content": "次の質問"},
            ],
        )

    def test_supplied_conversation_id_selects_and_updates_that_history(self):
        selected = self.service.create_active_conversation(title="selected")
        other = self.service.create_active_conversation(title="other")
        client = Mock()
        client.responses.create.return_value = [text_delta("続きの回答")]

        with (
            patch.object(chat_service, "client", client),
            patch.object(chat_service, "route_message", return_value="chat"),
            patch.object(chat_service, "load_system_prompt", return_value="system"),
            patch.object(
                chat_service,
                "format_memory_for_prompt",
                return_value="memory",
            ),
        ):
            chunks = list(
                chat_service.generate_chat_stream(
                    "続きを話す",
                    conversation_id=selected["id"],
                )
            )

        self.assertEqual(
            parse_sse_payloads(chunks)[0]["conversation_id"],
            selected["id"],
        )
        self.assertEqual(
            self.service.get_active_conversation()["id"],
            selected["id"],
        )
        self.assertEqual(
            [
                message["content"]
                for message in self.service.store.get_messages(selected["id"])
            ],
            ["続きを話す", "続きの回答"],
        )
        self.assertEqual(
            self.service.store.get_messages(other["id"]),
            [],
        )

    def test_note_task_and_memory_results_are_persisted(self):
        cases = (
            ("note", "handle_note_intent", "メモして", "note reply"),
            ("task", "handle_task_intent", "タスク追加", "task reply"),
            ("memory", "handle_memory_intent", "覚えて", "memory reply"),
        )

        for route, handler_name, message, reply in cases:
            with self.subTest(route=route):
                self.service.create_active_conversation(title=route)
                client = Mock()

                with (
                    patch.object(chat_service, "client", client),
                    patch.object(
                        chat_service,
                        "route_message",
                        return_value=route,
                    ),
                    patch.object(
                        chat_service,
                        handler_name,
                        return_value=reply,
                    ) as handler,
                ):
                    chunks = list(
                        chat_service.generate_chat_stream(message)
                    )

                conversation = self.service.get_active_conversation()
                conversation_id = conversation["id"]
                messages = self.service.store.get_messages(conversation_id)

                self.assertEqual(
                    parse_sse_payloads(chunks),
                    [
                        {
                            "user_message_id": messages[0]["id"],
                            "conversation_id": conversation_id,
                        },
                        {
                            "text": reply,
                            "assistant_message_id": messages[1]["id"],
                            "conversation_id": conversation_id,
                        },
                        {
                            "done": True,
                            "assistant_message_id": messages[1]["id"],
                            "conversation_id": conversation_id,
                        },
                    ],
                )
                handler.assert_called_once_with(message)
                client.responses.create.assert_not_called()
                self.assertEqual(
                    [(item["role"], item["content"]) for item in messages],
                    [("user", message), ("assistant", reply)],
                )
                self.assertEqual(
                    messages[1]["metadata"],
                    {"kind": "intent_result", "route": route},
                )

    def test_unhandled_specialized_route_falls_back_to_normal_chat(self):
        client = Mock()
        client.responses.create.return_value = [text_delta("fallback")]

        with (
            patch.object(chat_service, "client", client),
            patch.object(chat_service, "route_message", return_value="note"),
            patch.object(
                chat_service,
                "handle_note_intent",
                return_value=None,
            ),
            patch.object(chat_service, "load_system_prompt", return_value="system"),
            patch.object(
                chat_service,
                "format_memory_for_prompt",
                return_value="memory",
            ),
        ):
            list(chat_service.generate_chat_stream("メモの相談"))

        conversation = self.service.get_active_conversation()
        messages = self.service.store.get_messages(conversation["id"])

        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [
                ("user", "メモの相談"),
                ("assistant", "fallback"),
            ],
        )

    def test_streaming_exception_persists_partial_assistant_as_failed(self):
        def failing_stream():
            yield text_delta("途中まで")
            raise RuntimeError("stream failed")

        client = Mock()
        client.responses.create.return_value = failing_stream()

        with (
            patch.object(chat_service, "client", client),
            patch.object(chat_service, "route_message", return_value="chat"),
            patch.object(chat_service, "load_system_prompt", return_value="system"),
            patch.object(
                chat_service,
                "format_memory_for_prompt",
                return_value="memory",
            ),
        ):
            chunks = list(chat_service.generate_chat_stream("質問"))

        conversation = self.service.get_active_conversation()
        conversation_id = conversation["id"]
        messages = self.service.store.get_messages(conversation_id)

        self.assertEqual(
            parse_sse_payloads(chunks),
            [
                {
                    "user_message_id": messages[0]["id"],
                    "conversation_id": conversation_id,
                },
                {"text": "途中まで", "conversation_id": conversation_id},
                {
                    "error": "stream failed",
                    "assistant_message_id": messages[-1]["id"],
                    "conversation_id": conversation_id,
                },
            ],
        )
        self.assertEqual(messages[-1]["role"], "assistant")
        self.assertEqual(messages[-1]["content"], "途中まで")
        self.assertEqual(messages[-1]["status"], "failed")
        self.assertEqual(messages[-1]["error_message"], "stream failed")
        self.assertEqual(
            self.service.build_context(),
            [{"role": "user", "content": "質問"}],
        )

    def test_response_failed_event_is_persisted_as_failed(self):
        client = Mock()
        client.responses.create.return_value = [
            response_event(
                "response.failed",
                "failed-response",
                error_message="model failed",
            )
        ]

        with (
            patch.object(chat_service, "client", client),
            patch.object(chat_service, "route_message", return_value="chat"),
            patch.object(chat_service, "load_system_prompt", return_value="system"),
            patch.object(
                chat_service,
                "format_memory_for_prompt",
                return_value="memory",
            ),
        ):
            chunks = list(chat_service.generate_chat_stream("質問"))

        conversation = self.service.get_active_conversation()
        messages = self.service.store.get_messages(conversation["id"])

        self.assertEqual(parse_sse_payloads(chunks)[-1]["error"], "model failed")
        self.assertEqual(messages[-1]["status"], "failed")
        self.assertEqual(messages[-1]["response_id"], "failed-response")

    def test_closed_stream_persists_partial_assistant_as_failed(self):
        client = Mock()
        client.responses.create.return_value = [
            text_delta("途中"),
            text_delta("未送信"),
        ]

        with (
            patch.object(chat_service, "client", client),
            patch.object(chat_service, "route_message", return_value="chat"),
            patch.object(chat_service, "load_system_prompt", return_value="system"),
            patch.object(
                chat_service,
                "format_memory_for_prompt",
                return_value="memory",
            ),
        ):
            stream = chat_service.generate_chat_stream("質問")
            next(stream)
            text_payload = parse_sse_payloads([next(stream)])[0]
            stream.close()

        conversation = self.service.get_active_conversation()
        messages = self.service.store.get_messages(conversation["id"])

        self.assertEqual(text_payload["text"], "途中")
        self.assertEqual(messages[-1]["content"], "途中")
        self.assertEqual(messages[-1]["status"], "failed")
        self.assertEqual(
            messages[-1]["error_message"],
            "chat stream closed before completion",
        )


class ChatRouteConversationIdTests(unittest.TestCase):
    def test_chat_stream_accepts_and_passes_conversation_id(self):
        route = Path("app/routes/chat.py").read_text(encoding="utf-8")

        self.assertIn("conversation_id: str | None = None", route)
        self.assertIn(
            "conversation_id=request.conversation_id",
            route,
        )
        self.assertIn('media_type="text/event-stream"', route)

    def test_browser_tracks_conversation_id_from_stream(self):
        script = Path("static/script.js").read_text(encoding="utf-8")

        self.assertIn("let activeConversationId = null;", script)
        self.assertIn("conversation_id: activeConversationId", script)
        self.assertIn(
            "activeConversationId = data.conversation_id;",
            script,
        )


if __name__ == "__main__":
    unittest.main()
