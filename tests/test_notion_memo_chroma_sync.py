import hashlib
import unittest

from unittest.mock import Mock, call

from app.chunking.notion_chunker import NotionChunk
from app.chunking.notion_memo_chunker import NotionMemoChunker
from app.embeddings.embedding_service import EmbeddingRunResult
from app.integrations.notion_memo_reader import NotionMemoReader
from app.vector.chroma_index import ChromaIndexError, ChromaPageSyncResult
from app.vector.notion_chroma_sync import (
    NotionChromaSyncResult,
    NotionChromaSyncService,
)
from app.vector.notion_memo_chroma_sync import (
    NotionMemoChromaSyncService,
)


def memo(page_id: str, note_id: int, content: str):
    return {
        "id": note_id,
        "content": content,
        "notion_page_id": page_id,
    }


def chunk(page_id: str, content: str):
    return NotionChunk(
        chunk_id=f"notion-chunk:{page_id}",
        notion_page_id=page_id,
        block_id=f"block-{page_id}",
        title="Memo",
        chunk_index=0,
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        last_edited_time="2026-09-03T00:00:00Z",
        source_type="notion_memo",
        notion_url=f"https://www.notion.so/{page_id}",
        heading_path=("Memo",),
        block_ids=(f"block-{page_id}",),
    )


def sync_result(page_id: str, *, embedded: int, skipped: int, deleted: int):
    return NotionChromaSyncResult(
        notion_page_id=page_id,
        chunk_count=1,
        embedding_result=EmbeddingRunResult(
            total_chunks=1,
            embedded_chunks=embedded,
            skipped_unchanged=skipped,
            excluded_empty=0,
            api_batches=1 if embedded else 0,
        ),
        chroma_result=ChromaPageSyncResult(
            collection_name="test",
            current_chunks=1,
            upserted_chunks=1,
            deleted_chunks=deleted,
        ),
    )


class NotionMemoChromaSyncServiceTests(unittest.TestCase):
    def setUp(self):
        self.reader = Mock(spec=NotionMemoReader)
        self.chunker = Mock(spec=NotionMemoChunker)
        self.chroma_sync = Mock(spec=NotionChromaSyncService)

    def test_dry_run_reads_all_notes_and_never_writes(self):
        note_a = memo("page-a", 1, "AEC")
        note_b = memo("page-b", 2, "")
        chunk_a = chunk("page-a", "AEC")
        self.reader.list_notes_for_indexing.return_value = [note_a, note_b]
        self.chunker.chunk.side_effect = ([chunk_a], [])
        service = NotionMemoChromaSyncService(
            reader=self.reader,
            chunker=self.chunker,
            chroma_sync_service=self.chroma_sync,
        )

        result = service.sync_all(dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.total_pages, 2)
        self.assertEqual(result.pages_with_content, 1)
        self.assertEqual(result.empty_pages, 1)
        self.assertEqual(result.candidate_chunks, 1)
        self.assertEqual(result.synced_pages, 0)
        self.assertEqual(result.failures, ())
        self.chroma_sync.sync_chunks.assert_not_called()

    def test_apply_syncs_every_page_and_aggregates_restart_safe_counts(self):
        note_a = memo("page-a", 1, "AEC")
        note_b = memo("page-b", 2, "後回しの作業")
        chunk_a = chunk("page-a", "AEC")
        chunk_b = chunk("page-b", "後回しの作業")
        self.reader.list_notes_for_indexing.return_value = [note_a, note_b]
        self.chunker.chunk.side_effect = ([chunk_a], [chunk_b])
        self.chroma_sync.sync_chunks.side_effect = (
            sync_result("page-a", embedded=1, skipped=0, deleted=0),
            sync_result("page-b", embedded=0, skipped=1, deleted=2),
        )
        service = NotionMemoChromaSyncService(
            reader=self.reader,
            chunker=self.chunker,
            chroma_sync_service=self.chroma_sync,
        )

        result = service.sync_all(dry_run=False)

        self.assertFalse(result.dry_run)
        self.assertEqual(result.synced_pages, 2)
        self.assertEqual(result.embedded_chunks, 1)
        self.assertEqual(result.skipped_unchanged, 1)
        self.assertEqual(result.deleted_chunks, 2)
        self.assertEqual(
            self.chroma_sync.sync_chunks.call_args_list,
            [
                call(notion_page_id="page-a", chunks=[chunk_a]),
                call(notion_page_id="page-b", chunks=[chunk_b]),
            ],
        )

    def test_apply_continues_after_one_page_failure(self):
        note_a = memo("page-a", 1, "失敗")
        note_b = memo("page-b", 2, "成功")
        chunk_a = chunk("page-a", "失敗")
        chunk_b = chunk("page-b", "成功")
        self.reader.list_notes_for_indexing.return_value = [note_a, note_b]
        self.chunker.chunk.side_effect = ([chunk_a], [chunk_b])
        self.chroma_sync.sync_chunks.side_effect = (
            ChromaIndexError("一時的な同期失敗"),
            sync_result("page-b", embedded=1, skipped=0, deleted=0),
        )
        service = NotionMemoChromaSyncService(
            reader=self.reader,
            chunker=self.chunker,
            chroma_sync_service=self.chroma_sync,
        )

        result = service.sync_all(dry_run=False)

        self.assertEqual(result.synced_pages, 1)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].notion_page_id, "page-a")
        self.assertEqual(result.failures[0].local_id, 1)
        self.assertEqual(
            self.chroma_sync.sync_chunks.call_args_list[-1],
            call(notion_page_id="page-b", chunks=[chunk_b]),
        )

    def test_apply_empty_content_removes_existing_page_chunks(self):
        empty_note = memo("page-empty", 3, "")
        self.reader.list_notes_for_indexing.return_value = [empty_note]
        self.chunker.chunk.return_value = []
        self.chroma_sync.sync_chunks.return_value = NotionChromaSyncResult(
            notion_page_id="page-empty",
            chunk_count=0,
            embedding_result=EmbeddingRunResult(0, 0, 0, 0, 0),
            chroma_result=ChromaPageSyncResult("test", 0, 0, 2),
        )
        service = NotionMemoChromaSyncService(
            reader=self.reader,
            chunker=self.chunker,
            chroma_sync_service=self.chroma_sync,
        )

        result = service.sync_all(dry_run=False)

        self.assertEqual(result.empty_pages, 1)
        self.assertEqual(result.synced_pages, 1)
        self.assertEqual(result.deleted_chunks, 2)
        self.chroma_sync.sync_chunks.assert_called_once_with(
            notion_page_id="page-empty",
            chunks=[],
        )


if __name__ == "__main__":
    unittest.main()
