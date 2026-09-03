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

from app.services import intent_service, router_service


class RouterServiceBaselineTests(unittest.TestCase):
    def test_quick_routes_preserve_existing_keyword_priority(self):
        cases = (
            ("メモして", "note"),
            ("タスクを追加", "task"),
            ("TODOを見せて", "task"),
            ("やることを追加", "task"),
            ("これを覚えて", "memory"),
            ("記憶を見せて", "memory"),
            ("今日の未完了タスクを見せて", "task"),
            ("前にAECについてどう考えてた？", "knowledge_search"),
            ("最近後回しにしてた開発作業は？", "knowledge_search"),
            (
                "気分で音楽を選ぶ機能について考えたことは？",
                "knowledge_search",
            ),
            (
                "前にメモしたAECについてどう考えてた？",
                "knowledge_search",
            ),
            ("普通の相談です", None),
        )

        for message, expected in cases:
            with self.subTest(message=message):
                self.assertEqual(
                    router_service.quick_route_message(message),
                    expected,
                )

    def test_router_uses_ai_classification_when_quick_route_is_absent(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text='{"route": "task"}'
        )

        with (
            patch.object(router_service, "client", client),
            patch.object(
                router_service,
                "load_router_prompt",
                return_value="router prompt",
            ),
        ):
            route = router_service.route_message("今日することは？")

        self.assertEqual(route, "task")
        request = client.responses.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-5-mini")
        self.assertIn("今日することは？", request["input"])

    def test_router_falls_back_to_chat_for_invalid_ai_json(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text="not-json"
        )

        with (
            patch.object(router_service, "client", client),
            patch.object(
                router_service,
                "load_router_prompt",
                return_value="router prompt",
            ),
        ):
            self.assertEqual(router_service.route_message("相談"), "chat")

    def test_router_accepts_knowledge_search_from_ai_classification(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text='{"route": "knowledge_search"}'
        )

        with (
            patch.object(router_service, "client", client),
            patch.object(
                router_service,
                "load_router_prompt",
                return_value="router prompt",
            ),
        ):
            route = router_service.route_message("以前の構想を確認したい")

        self.assertEqual(route, "knowledge_search")

    def test_router_rejects_unknown_ai_route(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text='{"route": "delete_everything"}'
        )

        with patch.object(router_service, "client", client):
            self.assertEqual(router_service.route_message("相談"), "chat")


class IntentServiceBaselineTests(unittest.TestCase):
    def setUp(self):
        intent_service.pending_delete_all = False

    def tearDown(self):
        intent_service.pending_delete_all = False

    def test_note_actions_dispatch_to_existing_note_services(self):
        with (
            patch.object(
                intent_service,
                "classify_note_intent",
                return_value={"action": "add", "content": "買い物"},
            ),
            patch.object(
                intent_service,
                "add_note",
                return_value={"id": 4, "content": "買い物"},
            ) as add_note,
        ):
            self.assertEqual(
                intent_service.handle_note_intent("買い物をメモ"),
                "メモしておきました。\n4. 買い物",
            )
            add_note.assert_called_once_with("買い物")

        with (
            patch.object(
                intent_service,
                "classify_note_intent",
                return_value={"action": "list"},
            ),
            patch.object(
                intent_service,
                "format_notes_list",
                return_value="note list",
            ) as list_notes,
        ):
            self.assertEqual(
                intent_service.handle_note_intent("メモ一覧"),
                "note list",
            )
            list_notes.assert_called_once_with()

        with (
            patch.object(
                intent_service,
                "classify_note_intent",
                return_value={"action": "search", "keyword": "買い物"},
            ),
            patch.object(
                intent_service,
                "search_notes",
                return_value="note search",
            ) as search_notes,
        ):
            self.assertEqual(
                intent_service.handle_note_intent("買い物のメモ"),
                "note search",
            )
            search_notes.assert_called_once_with("買い物")

        with (
            patch.object(
                intent_service,
                "classify_note_intent",
                return_value={
                    "action": "delete",
                    "delete_all": False,
                    "note_ids": ["3", "5"],
                },
            ),
            patch.object(
                intent_service,
                "delete_notes",
                return_value="note deleted",
            ) as delete_notes,
        ):
            self.assertEqual(
                intent_service.handle_note_intent("3と5を削除"),
                "note deleted",
            )
            delete_notes.assert_called_once_with([3, 5])

    def test_note_delete_all_confirmation_preserves_existing_flow(self):
        with patch.object(
            intent_service,
            "delete_all_notes",
            return_value="all notes deleted",
        ) as delete_all_notes:
            self.assertEqual(
                intent_service.handle_note_intent("メモを全部削除"),
                "現在保存されているメモをすべて削除します。よろしいですか？",
            )
            delete_all_notes.assert_not_called()

            self.assertEqual(
                intent_service.handle_note_intent("はい"),
                "all notes deleted",
            )
            delete_all_notes.assert_called_once_with()
            self.assertFalse(intent_service.pending_delete_all)

    def test_task_actions_dispatch_to_existing_task_services(self):
        with (
            patch.object(
                intent_service,
                "classify_task_intent",
                return_value={
                    "action": "add",
                    "title": "テストを書く",
                    "due_date": "2026-08-20",
                },
            ),
            patch.object(
                intent_service,
                "add_task",
                return_value={
                    "id": 2,
                    "title": "テストを書く",
                    "due_date": "2026-08-20",
                },
            ) as add_task,
        ):
            self.assertIn(
                "2. テストを書く",
                intent_service.handle_task_intent("タスク追加"),
            )
            add_task.assert_called_once_with("テストを書く", "2026-08-20")

        with (
            patch.object(
                intent_service,
                "classify_task_intent",
                return_value={"action": "list", "status_filter": "todo"},
            ),
            patch.object(
                intent_service,
                "format_tasks_list",
                return_value="task list",
            ) as list_tasks,
        ):
            self.assertEqual(
                intent_service.handle_task_intent("未完了タスク"),
                "task list",
            )
            list_tasks.assert_called_once_with("todo")

        with (
            patch.object(
                intent_service,
                "classify_task_intent",
                return_value={"action": "search", "keyword": "テスト"},
            ),
            patch.object(
                intent_service,
                "search_tasks",
                return_value="task search",
            ) as search_tasks,
        ):
            self.assertEqual(
                intent_service.handle_task_intent("テストのタスク"),
                "task search",
            )
            search_tasks.assert_called_once_with("テスト")

        with (
            patch.object(
                intent_service,
                "classify_task_intent",
                return_value={"action": "complete", "task_ids": ["2", "4"]},
            ),
            patch.object(
                intent_service,
                "complete_tasks",
                return_value="tasks completed",
            ) as complete_tasks,
        ):
            self.assertEqual(
                intent_service.handle_task_intent("2と4を完了"),
                "tasks completed",
            )
            complete_tasks.assert_called_once_with([2, 4])

        with (
            patch.object(
                intent_service,
                "classify_task_intent",
                return_value={"action": "delete", "task_ids": ["6"]},
            ),
            patch.object(
                intent_service,
                "delete_tasks",
                return_value="task deleted",
            ) as delete_tasks,
        ):
            self.assertEqual(
                intent_service.handle_task_intent("6を削除"),
                "task deleted",
            )
            delete_tasks.assert_called_once_with([6])

    def test_memory_actions_dispatch_to_existing_memory_services(self):
        with (
            patch.object(
                intent_service,
                "classify_memory_intent",
                return_value={
                    "action": "add",
                    "content": "Pythonが好き",
                    "category": "preference",
                },
            ),
            patch.object(
                intent_service,
                "add_memory",
                return_value={
                    "id": 8,
                    "content": "Pythonが好き",
                    "category": "preference",
                },
            ) as add_memory,
        ):
            self.assertIn(
                "8. [preference] Pythonが好き",
                intent_service.handle_memory_intent("覚えて"),
            )
            add_memory.assert_called_once_with("Pythonが好き", "preference")

        with (
            patch.object(
                intent_service,
                "classify_memory_intent",
                return_value={"action": "list"},
            ),
            patch.object(
                intent_service,
                "format_memory_list",
                return_value="memory list",
            ) as list_memory,
        ):
            self.assertEqual(
                intent_service.handle_memory_intent("記憶一覧"),
                "memory list",
            )
            list_memory.assert_called_once_with()

        with (
            patch.object(
                intent_service,
                "classify_memory_intent",
                return_value={"action": "search", "keyword": "Python"},
            ),
            patch.object(
                intent_service,
                "search_memory",
                return_value="memory search",
            ) as search_memory,
        ):
            self.assertEqual(
                intent_service.handle_memory_intent("Pythonを覚えてる？"),
                "memory search",
            )
            search_memory.assert_called_once_with("Python")

        with (
            patch.object(
                intent_service,
                "classify_memory_intent",
                return_value={
                    "action": "update",
                    "memory_ids": ["8"],
                    "content": "PythonとRustが好き",
                    "category": "preference",
                },
            ),
            patch.object(
                intent_service,
                "update_memory",
                return_value="memory updated",
            ) as update_memory,
        ):
            self.assertEqual(
                intent_service.handle_memory_intent("8番を更新"),
                "memory updated",
            )
            update_memory.assert_called_once_with(
                [8],
                "PythonとRustが好き",
                "preference",
            )

        with (
            patch.object(
                intent_service,
                "classify_memory_intent",
                return_value={"action": "delete", "memory_ids": ["8"]},
            ),
            patch.object(
                intent_service,
                "delete_memory",
                return_value="memory deleted",
            ) as delete_memory,
        ):
            self.assertEqual(
                intent_service.handle_memory_intent("8番を削除"),
                "memory deleted",
            )
            delete_memory.assert_called_once_with([8])


if __name__ == "__main__":
    unittest.main()
