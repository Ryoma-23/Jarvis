import hashlib
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

from app.chunking.notion_chunker import NotionChunk
from app.embeddings.embedding_store import EmbeddingStore
from app.integrations.notion_client import NotionClient
from app.integrations.openai_embedding_client import OpenAIEmbeddingClient
from scripts.embed_notion_page import embed_notion_page


class EmbedNotionPageCommandTests(unittest.TestCase):
    def test_chunks_page_and_persists_only_missing_embedding(self):
        content = "Notion Page content"
        chunk = NotionChunk(
            chunk_id="notion-chunk:test",
            notion_page_id="page-id",
            block_id="block-id",
            title="Test",
            chunk_index=0,
            content=content,
            content_hash=hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest(),
            last_edited_time="2026-08-30T00:00:00+00:00",
            source_type="notion_page",
            notion_url="https://www.notion.so/test",
            heading_path=("Test",),
            block_ids=("block-id",),
        )
        notion_client = Mock(spec=NotionClient)
        embedding_client = Mock(spec=OpenAIEmbeddingClient)
        embedding_client.create_embeddings.return_value = [[0.1, 0.2]]

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = EmbeddingStore(
                Path(temporary_directory) / "embeddings.sqlite3"
            )

            with patch(
                "scripts.embed_notion_page.NotionPageChunkingService"
            ) as chunking_service_type:
                chunking_service_type.return_value.chunk_page.return_value = [
                    chunk
                ]
                result = embed_notion_page(
                    "page-id",
                    notion_client=notion_client,
                    embedding_client=embedding_client,
                    store=store,
                    model="text-embedding-3-small",
                    dimensions=2,
                    batch_size=10,
                )

            self.assertEqual(result.embedded_chunks, 1)
            self.assertEqual(store.count(), 1)
            chunking_service_type.assert_called_once_with(
                client=notion_client
            )
            chunking_service_type.return_value.chunk_page.assert_called_once_with(
                "page-id"
            )


if __name__ == "__main__":
    unittest.main()
