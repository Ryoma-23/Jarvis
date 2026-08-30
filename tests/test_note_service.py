import json
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

from app.integrations.notion_client import NotionConnectionError
from app.integrations.notion_memo_reader import NotionMemoReader
from app.integrations.notion_memo_writer import (
    NotionMemoSyncResult,
    NotionMemoWriter,
)
from app.repositories.note_repository import NoteRepository
from app.services import intent_service, note_service
from app.services.realtime_tools import note_tools


class NoteRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.notes_file = Path(self.temp_directory.name) / "notes.json"
        self.writer = Mock(spec=NotionMemoWriter)
        self.reader = Mock(spec=NotionMemoReader)

    def tearDown(self):
        self.temp_directory.cleanup()

    def repository(self, *, read_from_notion=False):
        return NoteRepository(
            local_path=self.notes_file,
            notion_writer=self.writer,
            notion_reader=self.reader,
            read_from_notion=read_from_notion,
        )

    def test_local_note_is_saved_before_notion_and_mapping_is_persisted(self):
        repository = self.repository()

        def sync_note(note):
            stored = json.loads(
                self.notes_file.read_text(encoding="utf-8")
            )
            self.assertEqual(stored[0]["notion_sync_status"], "pending")
            return NotionMemoSyncResult(
                page_id="notion-page-id",
                already_existed=False,
            )

        self.writer.sync_note.side_effect = sync_note

        note = repository.add("牛乳を買う")

        stored = repository.load_all_local()
        self.assertEqual(note["notion_sync_status"], "synced")
        self.assertEqual(note["notion_page_id"], "notion-page-id")
        self.assertEqual(stored[0]["notion_page_id"], "notion-page-id")

    def test_notion_failure_keeps_local_note_pending(self):
        self.writer.sync_note.side_effect = NotionConnectionError(
            "Notion unavailable"
        )
        repository = self.repository()

        note = repository.add("ローカルには残す")

        self.assertEqual(note["notion_sync_status"], "pending")
        self.assertEqual(repository.list()[0]["content"], "ローカルには残す")

    def test_local_failure_prevents_notion_write(self):
        repository = self.repository()

        with patch.object(
            repository.local,
            "save",
            side_effect=OSError("disk unavailable"),
        ):
            with self.assertRaises(OSError):
                repository.add("保存できない")

        self.writer.sync_note.assert_not_called()

    def test_delete_keeps_tombstone_and_trashes_notion_page(self):
        repository = self.repository()
        repository.save_all_local(
            [
                {
                    "id": 4,
                    "content": "削除する",
                    "created_at": "2026-08-30 12:00:00",
                    "created_at_iso": "2026-08-30T12:00:00+09:00",
                    "sync_key": "sync-4",
                    "notion_page_id": "page-4",
                    "notion_sync_status": "synced",
                }
            ]
        )

        deleted = repository.delete([4])

        stored = repository.load_all_local()[0]
        self.assertEqual(deleted, [4])
        self.assertTrue(stored["deleted_at"])
        self.assertEqual(stored["notion_sync_status"], "deleted")
        self.assertEqual(repository.list(), [])
        self.writer.trash_page.assert_called_once_with("page-4")

    def test_notion_trash_failure_remains_retryable_and_hidden(self):
        self.writer.trash_page.side_effect = NotionConnectionError("offline")
        repository = self.repository()
        repository.save_all_local(
            [
                {
                    "id": 5,
                    "content": "削除待ち",
                    "created_at": "2026-08-30 12:00:00",
                    "notion_page_id": "page-5",
                    "notion_sync_status": "synced",
                }
            ]
        )

        repository.delete([5])

        stored = repository.load_all_local()[0]
        self.assertEqual(stored["notion_sync_status"], "delete_pending")
        self.assertEqual(repository.list(), [])

    def test_migration_dry_run_does_not_mutate_local_or_create_page(self):
        repository = self.repository()
        legacy = {
            "id": 6,
            "content": "既存メモ",
            "created_at": "2026-08-30 13:00:00",
        }
        repository.save_all_local([legacy])
        before = self.notes_file.read_text(encoding="utf-8")
        self.writer.find_page_id_by_sync_key.return_value = None

        result = repository.migrate(dry_run=True)

        self.assertEqual(result.would_create, 1)
        self.assertEqual(result.migrated, 0)
        self.assertEqual(
            self.notes_file.read_text(encoding="utf-8"),
            before,
        )
        self.writer.sync_note.assert_not_called()

    def test_migration_apply_reuses_existing_page(self):
        repository = self.repository()
        repository.save_all_local(
            [
                {
                    "id": 7,
                    "content": "重複させない",
                    "created_at": "2026-08-30 14:00:00",
                }
            ]
        )
        self.writer.find_page_id_by_sync_key.return_value = "existing-page"
        self.writer.sync_note.return_value = NotionMemoSyncResult(
            page_id="existing-page",
            already_existed=True,
        )

        result = repository.migrate(dry_run=False)

        stored = repository.load_all_local()[0]
        self.assertEqual(result.existing_in_notion, 1)
        self.assertEqual(stored["notion_page_id"], "existing-page")
        self.assertEqual(stored["notion_sync_status"], "synced")

    def test_feature_flag_reads_notion_and_failure_falls_back_local(self):
        local_note = {
            "id": 8,
            "content": "Local fallback",
            "created_at": "2026-08-30 15:00:00",
        }
        notion_note = {
            "id": 9,
            "content": "Notion read",
            "created_at": "2026-08-30 16:00:00",
        }
        repository = self.repository(read_from_notion=True)
        repository.save_all_local([local_note])
        self.reader.list_notes.return_value = [notion_note]

        self.assertEqual(repository.list(), [notion_note])

        self.reader.list_notes.side_effect = NotionConnectionError("offline")
        self.assertEqual(repository.list(), [local_note])


class NoteServiceBoundaryTests(unittest.TestCase):
    def test_text_and_realtime_responses_keep_existing_format(self):
        repository = Mock(spec=NoteRepository)
        repository.add.side_effect = (
            {"id": 1, "content": "テキストメモ"},
            {"id": 2, "content": "音声メモ"},
        )

        with (
            patch.object(
                note_service,
                "get_note_repository",
                return_value=repository,
            ),
            patch.object(
                intent_service,
                "classify_note_intent",
                return_value={"action": "add", "content": "テキストメモ"},
            ),
            patch.object(
                intent_service,
                "add_note",
                side_effect=note_service.add_note,
            ),
            patch.object(
                note_tools,
                "add_note",
                side_effect=note_service.add_note,
            ),
        ):
            text_result = intent_service.handle_note_intent("メモして")
            realtime_result = note_tools.tool_add_note(
                {"content": "音声メモ"}
            )

        self.assertEqual(
            text_result,
            "メモしておきました。\n1. テキストメモ",
        )
        self.assertEqual(
            realtime_result,
            {
                "success": True,
                "message": "メモしておきました。2. 音声メモ",
            },
        )


if __name__ == "__main__":
    unittest.main()
