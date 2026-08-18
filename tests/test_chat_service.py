import json
import sys
import unittest
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import Mock, patch


if "app.openai_client" not in sys.modules:
    openai_client_stub = ModuleType("app.openai_client")
    openai_client_stub.client = Mock()
    openai_client_stub.api_key = "test-api-key"
    sys.modules["app.openai_client"] = openai_client_stub

from app.services import chat_service


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


class ChatServiceConversationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.original_history = chat_service.conversation_history
        chat_service.conversation_history = []

    def tearDown(self):
        chat_service.conversation_history = self.original_history

    def test_normal_chat_streams_text_and_appends_user_and_assistant(self):
        client = Mock()
        client.responses.create.return_value = [
            text_delta("こんにちは"),
            SimpleNamespace(type="response.completed"),
            text_delta("。"),
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

        self.assertEqual(
            parse_sse_payloads(chunks),
            [
                {"text": "こんにちは"},
                {"text": "。"},
                {"done": True},
            ],
        )
        self.assertEqual(
            chat_service.conversation_history,
            [
                {"role": "user", "content": "こんにちは"},
                {"role": "assistant", "content": "こんにちは。"},
            ],
        )

        request = client.responses.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-5-mini")
        self.assertTrue(request["stream"])
        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertEqual(request["input"][0]["content"], "system prompt")
        self.assertEqual(request["input"][2]["content"], "memory context")
        self.assertEqual(
            request["input"][-1],
            {"role": "user", "content": "こんにちは"},
        )

    def test_history_is_trimmed_to_max_history_after_each_new_turn(self):
        chat_service.conversation_history = [
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"old-{index}",
            }
            for index in range(chat_service.MAX_HISTORY)
        ]

        client = Mock()
        client.responses.create.return_value = [text_delta("new-answer")]

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
            list(chat_service.generate_chat_stream("new-question"))

        self.assertEqual(
            len(chat_service.conversation_history),
            chat_service.MAX_HISTORY,
        )
        self.assertEqual(
            chat_service.conversation_history[0]["content"],
            "old-2",
        )
        self.assertEqual(
            chat_service.conversation_history[-2:],
            [
                {"role": "user", "content": "new-question"},
                {"role": "assistant", "content": "new-answer"},
            ],
        )

    def test_note_task_and_memory_routes_return_without_chat_completion(self):
        cases = (
            ("note", "handle_note_intent", "メモして", "note reply"),
            ("task", "handle_task_intent", "タスク追加", "task reply"),
            ("memory", "handle_memory_intent", "覚えて", "memory reply"),
        )

        for route, handler_name, message, reply in cases:
            with self.subTest(route=route):
                chat_service.conversation_history = []
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
                    chunks = list(chat_service.generate_chat_stream(message))

                self.assertEqual(
                    parse_sse_payloads(chunks),
                    [{"text": reply}, {"done": True}],
                )
                handler.assert_called_once_with(message)
                client.responses.create.assert_not_called()
                self.assertEqual(chat_service.conversation_history, [])

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
            chunks = list(chat_service.generate_chat_stream("メモの相談"))

        self.assertEqual(
            parse_sse_payloads(chunks),
            [{"text": "fallback"}, {"done": True}],
        )
        self.assertEqual(
            chat_service.conversation_history[-2:],
            [
                {"role": "user", "content": "メモの相談"},
                {"role": "assistant", "content": "fallback"},
            ],
        )

    def test_streaming_error_is_returned_as_an_sse_error(self):
        client = Mock()
        client.responses.create.side_effect = RuntimeError("stream failed")

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

        self.assertEqual(
            parse_sse_payloads(chunks),
            [{"error": "stream failed"}],
        )
        self.assertEqual(
            chat_service.conversation_history,
            [{"role": "user", "content": "質問"}],
        )


if __name__ == "__main__":
    unittest.main()
