import json
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

from app.integrations.notion_client import NotionConnectionError
from app.integrations.notion_memo_writer import (
    NotionMemoSyncResult,
    NotionMemoWriter,
)
from app.services import intent_service, note_service
from app.services.realtime_tools import note_tools


class NoteServiceNotionWriteTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.data_directory = Path(self.temp_directory.name)
        self.notes_file = self.data_directory / "notes.json"
        self.data_patch = patch.object(
            note_service,
            "DATA_DIR",
            self.data_directory,
        )
        self.file_patch = patch.object(
            note_service,
            "NOTES_FILE",
            self.notes_file,
        )
        self.data_patch.start()
        self.file_patch.start()
        note_service._build_notion_memo_writer.cache_clear()

    def tearDown(self):
        note_service._build_notion_memo_writer.cache_clear()
        self.file_patch.stop()
        self.data_patch.stop()
        self.temp_directory.cleanup()

    def test_local_note_is_saved_before_notion_and_metadata_is_persisted(self):
        writer = Mock(spec=NotionMemoWriter)

        def sync_note(note):
            stored = json.loads(self.notes_file.read_text(encoding="utf-8"))
            self.assertEqual(stored[0]["content"], "牛乳を買う")
            self.assertEqual(stored[0]["notion_sync_status"], "pending")
            return NotionMemoSyncResult(
                page_id="notion-page-id",
                already_existed=False,
            )

        writer.sync_note.side_effect = sync_note

        with patch.object(
            note_service,
            "get_notion_memo_writer",
            return_value=writer,
        ):
            note = note_service.add_note("牛乳を買う")

        stored = json.loads(self.notes_file.read_text(encoding="utf-8"))
        self.assertEqual(note["notion_sync_status"], "synced")
        self.assertEqual(note["notion_page_id"], "notion-page-id")
        self.assertEqual(stored[0]["notion_page_id"], "notion-page-id")
        self.assertTrue(stored[0]["sync_key"].startswith("jarvis-note:1:"))

    def test_notion_failure_leaves_local_note_pending(self):
        writer = Mock(spec=NotionMemoWriter)
        writer.sync_note.side_effect = NotionConnectionError(
            "Notion unavailable"
        )

        with patch.object(
            note_service,
            "get_notion_memo_writer",
            return_value=writer,
        ):
            note = note_service.add_note("ローカルには残す")

        stored = json.loads(self.notes_file.read_text(encoding="utf-8"))
        self.assertEqual(note["notion_sync_status"], "pending")
        self.assertIsNone(note["notion_page_id"])
        self.assertEqual(stored[0]["content"], "ローカルには残す")

    def test_pending_retry_reuses_same_local_note(self):
        writer = Mock(spec=NotionMemoWriter)
        writer.sync_note.side_effect = (
            NotionConnectionError("timeout"),
            NotionMemoSyncResult(
                page_id="existing-notion-page-id",
                already_existed=True,
            ),
        )

        with patch.object(
            note_service,
            "get_notion_memo_writer",
            return_value=writer,
        ):
            original = note_service.add_note("再試行するメモ")
            result = note_service.retry_pending_notion_notes()

        stored = json.loads(self.notes_file.read_text(encoding="utf-8"))
        self.assertEqual(original["id"], 1)
        self.assertEqual(result, {"attempted": 1, "synced": 1, "pending": 0})
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["id"], 1)
        self.assertEqual(
            stored[0]["notion_page_id"],
            "existing-notion-page-id",
        )
        self.assertEqual(writer.sync_note.call_count, 2)

    def test_local_failure_prevents_notion_write(self):
        writer = Mock(spec=NotionMemoWriter)

        with (
            patch.object(
                note_service,
                "get_notion_memo_writer",
                return_value=writer,
            ),
            patch.object(
                note_service,
                "save_notes",
                side_effect=OSError("disk unavailable"),
            ),
        ):
            with self.assertRaises(OSError):
                note_service.add_note("保存できない")

        writer.sync_note.assert_not_called()

    def test_text_and_realtime_responses_keep_existing_format(self):
        writer = Mock(spec=NotionMemoWriter)
        writer.sync_note.side_effect = lambda note: NotionMemoSyncResult(
            page_id=f"notion-page-{note['id']}",
            already_existed=False,
        )

        with (
            patch.object(
                note_service,
                "get_notion_memo_writer",
                return_value=writer,
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
        self.assertEqual(writer.sync_note.call_count, 2)


if __name__ == "__main__":
    unittest.main()
