import tempfile
import unittest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.chunking.notion_memo_chunker import NotionMemoChunker
from app.integrations.notion_client import (
    NotionConnectionError,
    NotionResponseError,
)
from app.integrations.notion_memo_reader import NotionMemoReader
from app.knowledge_sync.memo_indexer import MemoKnowledgeIndexer
from app.knowledge_sync.state import KnowledgeSyncStateStore
from app.vector.chroma_index import ChromaIndex
from app.vector.notion_chroma_sync import NotionChromaSyncService


PAGE_ID = "11111111-2222-3333-4444-555555555555"
EDITED_AT = "2026-09-13T06:00:00.000Z"


class MemoKnowledgeIndexerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.reader = Mock(spec=NotionMemoReader)
        self.chunker = Mock(spec=NotionMemoChunker)
        self.chroma_sync = Mock(spec=NotionChromaSyncService)
        self.chroma_index = Mock(spec=ChromaIndex)
        self.chroma_index.collection_name = "test-collection"
        self.state_store = KnowledgeSyncStateStore(
            Path(self.temporary_directory.name) / "sync-state.json"
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def indexer(self, *, retry_count=3, sleeper=None):
        arguments = {
            "reader": self.reader,
            "chunker": self.chunker,
            "chroma_sync_service": self.chroma_sync,
            "chroma_index": self.chroma_index,
            "state_store": self.state_store,
            "embedding_model": "embedding-model",
            "embedding_dimensions": 3,
            "retry_count": retry_count,
        }

        if sleeper is not None:
            arguments["sleeper"] = sleeper

        return MemoKnowledgeIndexer(**arguments)

    def test_fetches_full_memo_syncs_one_page_and_records_state(self):
        memo = _memo()
        chunks = [Mock(), Mock()]
        self.reader.get_by_page_id_for_indexing.return_value = memo
        self.chunker.chunk.return_value = chunks
        self.chroma_sync.sync_chunks.return_value = _sync_result(2)

        result = self.indexer().sync_page(PAGE_ID)

        self.reader.get_by_page_id_for_indexing.assert_called_once_with(
            PAGE_ID
        )
        self.chunker.chunk.assert_called_once_with(memo)
        self.chroma_sync.sync_chunks.assert_called_once_with(
            notion_page_id=PAGE_ID,
            chunks=chunks,
        )
        self.assertEqual(result.chunk_count, 2)
        self.assertEqual(result.embedded_chunks, 1)
        state = self.state_store.load(
            collection_name="test-collection",
            embedding_model="embedding-model",
            embedding_dimensions=3,
        )
        record = state.pages[PAGE_ID.replace("-", "")]
        self.assertEqual(record["source_type"], "notion_memo")
        self.assertEqual(record["last_edited_time"], EDITED_AT)
        self.assertEqual(record["chunk_count"], 2)

    def test_transient_read_failure_is_retried(self):
        self.reader.get_by_page_id_for_indexing.side_effect = [
            NotionConnectionError("temporary"),
            _memo(),
        ]
        self.chunker.chunk.return_value = []
        self.chroma_sync.sync_chunks.return_value = _sync_result(0)
        sleeper = Mock()

        self.indexer(
            retry_count=2,
            sleeper=sleeper,
        ).sync_page(PAGE_ID)

        self.assertEqual(
            self.reader.get_by_page_id_for_indexing.call_count,
            2,
        )
        sleeper.assert_called_once_with(1.0)

    def test_rejects_a_different_retrieved_page(self):
        self.reader.get_by_page_id_for_indexing.return_value = {
            **_memo(),
            "notion_page_id": "different-page",
        }

        with self.assertRaises(NotionResponseError):
            self.indexer().sync_page(PAGE_ID)

        self.chroma_sync.sync_chunks.assert_not_called()


def _memo():
    return {
        "id": 1,
        "content": "完全なMemo Content",
        "notion_page_id": PAGE_ID,
        "notion_title": "即時同期Memo",
        "notion_url": "https://www.notion.so/test",
        "notion_last_edited_time": EDITED_AT,
    }


def _sync_result(chunk_count):
    return SimpleNamespace(
        chunk_count=chunk_count,
        embedding_result=SimpleNamespace(
            embedded_chunks=1 if chunk_count else 0,
            skipped_unchanged=max(0, chunk_count - 1),
        ),
        chroma_result=SimpleNamespace(deleted_chunks=0),
    )


if __name__ == "__main__":
    unittest.main()
