import hashlib
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock

from app.chunking.notion_chunker import (
    NotionChunk,
    NotionPageChunkingService,
)
from app.embeddings.embedding_service import EmbeddingService
from app.embeddings.embedding_store import EmbeddingStore
from app.integrations.openai_embedding_client import OpenAIEmbeddingClient
from app.vector.chroma_index import ChromaIndex
from app.vector.chroma_index import ChromaIndexError
from app.vector.notion_chroma_sync import NotionChromaSyncService


PAGE_ID = "11111111-2222-3333-4444-555555555555"
MODEL = "text-embedding-3-small"
DIMENSIONS = 3


def _chunk(name, content, index):
    return NotionChunk(
        chunk_id=f"notion-chunk:{name}",
        notion_page_id=PAGE_ID,
        block_id=f"block-{name}",
        title="Pipeline Test",
        chunk_index=index,
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        last_edited_time="2026-08-30T00:00:00+00:00",
        source_type="notion_page",
        notion_url="https://www.notion.so/pipeline-test",
        heading_path=("Pipeline",),
        block_ids=(f"block-{name}",),
    )


class NotionChromaSyncServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        )
        root = Path(self.temporary_directory.name)
        self.embedding_store = EmbeddingStore(root / "embeddings.sqlite3")
        self.chroma_index = ChromaIndex(
            model=MODEL,
            dimensions=DIMENSIONS,
            persistence_path=root / "chroma",
        )
        self.embedding_client = Mock(spec=OpenAIEmbeddingClient)
        self.embedding_service = EmbeddingService(
            client=self.embedding_client,
            store=self.embedding_store,
            model=MODEL,
            dimensions=DIMENSIONS,
            batch_size=10,
        )
        self.chunking_service = Mock(spec=NotionPageChunkingService)
        self.service = NotionChromaSyncService(
            chunking_service=self.chunking_service,
            embedding_service=self.embedding_service,
            embedding_store=self.embedding_store,
            chroma_index=self.chroma_index,
            model=MODEL,
            dimensions=DIMENSIONS,
        )

    def tearDown(self):
        self.chroma_index.close()
        self.temporary_directory.cleanup()

    def test_syncs_phase5_chunks_through_embedding_store_to_chroma(self):
        chunk_a = _chunk("a", "First content", 0)
        chunk_b = _chunk("b", "Removed content", 1)
        chunk_c = _chunk("c", "Added content", 1)
        self.chunking_service.chunk_page.side_effect = (
            [chunk_a, chunk_b],
            [chunk_a, chunk_c],
        )
        self.embedding_client.create_embeddings.side_effect = (
            [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            [[0.7, 0.8, 0.9]],
        )

        first = self.service.sync_page(PAGE_ID)
        second = self.service.sync_page(PAGE_ID)

        self.assertEqual(first.embedding_result.embedded_chunks, 2)
        self.assertEqual(first.chroma_result.deleted_chunks, 0)
        self.assertEqual(second.embedding_result.embedded_chunks, 1)
        self.assertEqual(second.embedding_result.skipped_unchanged, 1)
        self.assertEqual(second.chroma_result.deleted_chunks, 1)
        self.assertEqual(
            self.chroma_index.get_page_chunk_ids(PAGE_ID),
            ("notion-chunk:a", "notion-chunk:c"),
        )
        records = self.chroma_index.get_page_records(PAGE_ID)
        metadata_by_id = dict(
            zip(records["ids"], records["metadatas"], strict=True)
        )
        self.assertEqual(
            metadata_by_id["notion-chunk:a"]["notion_page_id"],
            PAGE_ID,
        )
        self.assertEqual(
            metadata_by_id["notion-chunk:a"]["title"],
            "Pipeline Test",
        )

    def test_syncs_prebuilt_chunks_without_refetching_notion_page(self):
        chunk = _chunk("memo", "Memo property content", 0)
        self.embedding_client.create_embeddings.return_value = [
            [0.1, 0.2, 0.3]
        ]

        result = self.service.sync_chunks(
            notion_page_id=PAGE_ID,
            chunks=[chunk],
        )

        self.assertEqual(result.chunk_count, 1)
        self.chunking_service.chunk_page.assert_not_called()
        self.assertEqual(
            self.chroma_index.get_page_chunk_ids(PAGE_ID),
            ("notion-chunk:memo",),
        )

    def test_rejects_prebuilt_chunk_from_another_page(self):
        chunk = _chunk("wrong-page", "Wrong page content", 0)
        chunk = NotionChunk(
            **{
                **chunk.to_dict(),
                "notion_page_id": "another-page-id",
                "heading_path": chunk.heading_path,
                "block_ids": chunk.block_ids,
            }
        )

        with self.assertRaisesRegex(ChromaIndexError, "一致しません"):
            self.service.sync_chunks(
                notion_page_id=PAGE_ID,
                chunks=[chunk],
            )

        self.embedding_client.create_embeddings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
