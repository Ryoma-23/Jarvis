import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

from app.integrations.notion_client import NotionConnectionError
from app.integrations.notion_memory_store import NotionMemoryStore
from app.integrations.notion_store import NotionRecordSyncResult
from app.integrations.notion_task_store import NotionTaskStore
from app.repositories.memory_repository import MemoryRepository
from app.repositories.task_repository import TaskRepository
from app.services import memory_service, task_service


class TaskRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.tasks_file = Path(self.temp_directory.name) / "tasks.json"
        self.notion = Mock(spec=NotionTaskStore)
        self.notion.sync_task.return_value = NotionRecordSyncResult(
            page_id="task-page",
            already_existed=False,
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def repository(self, *, read_from_notion=False):
        return TaskRepository(
            local_path=self.tasks_file,
            notion_store=self.notion,
            read_from_notion=read_from_notion,
        )

    def test_add_and_complete_dual_write_status_and_completed_at(self):
        repository = self.repository()

        task = repository.add("テストを書く", "2026-09-01")
        completed = repository.complete([task["id"]])

        stored = repository.load_all_local()[0]
        synced_task = self.notion.sync_task.call_args_list[-1].args[0]
        self.assertEqual(completed, [1])
        self.assertEqual(stored["status"], "done")
        self.assertTrue(stored["completed_at"])
        self.assertTrue(stored["completed_at_iso"])
        self.assertEqual(stored["notion_page_id"], "task-page")
        self.assertEqual(synced_task["status"], "done")
        self.assertEqual(
            synced_task["completed_at_iso"],
            stored["completed_at_iso"],
        )

    def test_delete_keeps_tombstone_and_trashes_page(self):
        repository = self.repository()
        repository.save_all_local(
            [
                {
                    "id": 2,
                    "title": "削除するTask",
                    "status": "todo",
                    "due_date": None,
                    "created_at": "2026-08-30 12:00:00",
                    "notion_page_id": "task-page-2",
                    "notion_sync_status": "synced",
                }
            ]
        )

        repository.delete([2])

        stored = repository.load_all_local()[0]
        self.assertTrue(stored["deleted_at"])
        self.assertEqual(stored["notion_sync_status"], "deleted")
        self.assertEqual(repository.list(), [])
        self.notion.trash_page.assert_called_once_with("task-page-2")

    def test_read_failure_falls_back_to_local(self):
        repository = self.repository(read_from_notion=True)
        local_task = {
            "id": 3,
            "title": "Local Task",
            "status": "todo",
            "due_date": None,
            "created_at": "2026-08-30 12:00:00",
        }
        repository.save_all_local([local_task])
        self.notion.list_tasks.side_effect = NotionConnectionError("offline")

        self.assertEqual(repository.list(), [local_task])

    def test_task_service_response_format_is_unchanged(self):
        repository = Mock(spec=TaskRepository)
        repository.list.return_value = [
            {
                "id": 4,
                "title": "表示Task",
                "status": "todo",
                "due_date": None,
            }
        ]

        with patch.object(
            task_service,
            "get_task_repository",
            return_value=repository,
        ):
            result = task_service.format_tasks_list("todo")

        self.assertEqual(
            result,
            "未完了のタスクはこちらです。\n"
            "4. 表示Task / 未完了 / 期限: 期限なし",
        )


class MemoryRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.memory_file = Path(self.temp_directory.name) / "memory.json"
        self.notion = Mock(spec=NotionMemoryStore)
        self.notion.sync_memory.return_value = NotionRecordSyncResult(
            page_id="memory-page",
            already_existed=False,
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def repository(self, *, read_from_notion=False):
        return MemoryRepository(
            local_path=self.memory_file,
            notion_store=self.notion,
            read_from_notion=read_from_notion,
        )

    def test_add_and_update_dual_write_updated_at(self):
        repository = self.repository()

        memory = repository.add("Pythonが好き", "preference")
        updated = repository.update(
            [memory["id"]],
            "PythonとRustが好き",
            "preference",
        )

        stored = repository.load_all_local()[0]
        synced_memory = self.notion.sync_memory.call_args_list[-1].args[0]
        self.assertEqual(updated, [1])
        self.assertEqual(stored["content"], "PythonとRustが好き")
        self.assertTrue(stored["updated_at_iso"])
        self.assertEqual(stored["notion_page_id"], "memory-page")
        self.assertEqual(
            synced_memory["updated_at_iso"],
            stored["updated_at_iso"],
        )

    def test_delete_keeps_tombstone_and_trashes_page(self):
        repository = self.repository()
        repository.save_all_local(
            [
                {
                    "id": 2,
                    "content": "削除するMemory",
                    "category": "other",
                    "created_at": "2026-08-30 12:00:00",
                    "updated_at": "2026-08-30 12:00:00",
                    "notion_page_id": "memory-page-2",
                    "notion_sync_status": "synced",
                }
            ]
        )

        repository.delete([2])

        stored = repository.load_all_local()[0]
        self.assertTrue(stored["deleted_at"])
        self.assertEqual(stored["notion_sync_status"], "deleted")
        self.assertEqual(repository.list(), [])
        self.notion.trash_page.assert_called_once_with("memory-page-2")

    def test_prompt_keeps_full_memory_list_behavior(self):
        repository = Mock(spec=MemoryRepository)
        repository.list.return_value = [
            {
                "id": 3,
                "content": "コーヒーが好き",
                "category": "preference",
            },
            {
                "id": 4,
                "content": "東京在住",
                "category": "profile",
            },
        ]

        with patch.object(
            memory_service,
            "get_memory_repository",
            return_value=repository,
        ):
            result = memory_service.format_memory_for_prompt()

        self.assertIn("[preference] コーヒーが好き", result)
        self.assertIn("[profile] 東京在住", result)
        repository.list.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
