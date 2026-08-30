import hashlib
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, call

from app.chunking.notion_chunker import NotionChunk
from app.embeddings.embedding_service import (
    EmbeddingService,
    build_embedding_version,
)
from app.embeddings.embedding_store import EmbeddingStore
from app.integrations.openai_embedding_client import (
    EmbeddingAPIError,
    OpenAIEmbeddingClient,
)


MODEL = "text-embedding-3-small"
DIMENSIONS = 3


def _chunk(index, content):
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return NotionChunk(
        chunk_id=f"notion-chunk:{index}",
        notion_page_id="page-id",
        block_id=f"block-{index}",
        title="Embedding Test",
        chunk_index=index,
        content=content,
        content_hash=content_hash,
        last_edited_time="2026-08-30T10:00:00.000Z",
        source_type="notion_page",
        notion_url="https://www.notion.so/test",
        heading_path=("Test",),
        block_ids=(f"block-{index}",),
    )


def _vector(value):
    return [float(value)] * DIMENSIONS


class EmbeddingServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        db_path = Path(self.temporary_directory.name) / "embeddings.sqlite3"
        self.store = EmbeddingStore(db_path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _service(self, client, *, model=MODEL, dimensions=DIMENSIONS, batch=2):
        return EmbeddingService(
            client=client,
            store=self.store,
            model=model,
            dimensions=dimensions,
            batch_size=batch,
        )

    def test_excludes_empty_chunks_and_sends_nonempty_chunks_in_batches(self):
        client = Mock(spec=OpenAIEmbeddingClient)
        client.create_embeddings.side_effect = (
            [_vector(1), _vector(2)],
            [_vector(3)],
        )
        chunks = [
            _chunk(0, "first"),
            _chunk(1, "   "),
            _chunk(2, "second"),
            _chunk(3, "third"),
        ]

        result = self._service(client).embed_chunks(chunks)

        self.assertEqual(result.total_chunks, 4)
        self.assertEqual(result.embedded_chunks, 3)
        self.assertEqual(result.excluded_empty, 1)
        self.assertEqual(result.skipped_unchanged, 0)
        self.assertEqual(result.api_batches, 2)
        self.assertEqual(
            client.create_embeddings.call_args_list,
            [
                call(
                    ["first", "second"],
                    model=MODEL,
                    dimensions=DIMENSIONS,
                ),
                call(
                    ["third"],
                    model=MODEL,
                    dimensions=DIMENSIONS,
                ),
            ],
        )
        self.assertEqual(self.store.count(), 3)

    def test_same_version_is_skipped_without_calling_api_again(self):
        chunk = _chunk(0, "unchanged")
        first_client = Mock(spec=OpenAIEmbeddingClient)
        first_client.create_embeddings.return_value = [_vector(1)]
        self._service(first_client).embed_chunks([chunk])
        second_client = Mock(spec=OpenAIEmbeddingClient)

        result = self._service(second_client).embed_chunks([chunk])

        self.assertEqual(result.embedded_chunks, 0)
        self.assertEqual(result.skipped_unchanged, 1)
        self.assertEqual(result.api_batches, 0)
        second_client.create_embeddings.assert_not_called()
        record = self.store.list_records()[0]
        self.assertEqual(
            record["embedding_version"],
            build_embedding_version(
                content_hash=chunk.content_hash,
                model=MODEL,
                dimensions=DIMENSIONS,
            ),
        )
        self.assertEqual(record["model"], MODEL)
        self.assertEqual(record["dimensions"], DIMENSIONS)
        self.assertEqual(record["metadata"]["notion_page_id"], "page-id")

    def test_model_change_creates_a_new_version_and_keeps_old_record(self):
        chunk = _chunk(0, "same content")
        first_client = Mock(spec=OpenAIEmbeddingClient)
        first_client.create_embeddings.return_value = [_vector(1)]
        self._service(first_client).embed_chunks([chunk])
        second_client = Mock(spec=OpenAIEmbeddingClient)
        second_client.create_embeddings.return_value = [_vector(2)]

        result = self._service(
            second_client,
            model="text-embedding-3-large",
        ).embed_chunks([chunk])

        self.assertEqual(result.embedded_chunks, 1)
        self.assertEqual(self.store.count(), 2)
        self.assertEqual(
            {record["model"] for record in self.store.list_records()},
            {MODEL, "text-embedding-3-large"},
        )

    def test_embedding_version_changes_with_hash_model_or_dimensions(self):
        base = build_embedding_version(
            content_hash="hash-a",
            model=MODEL,
            dimensions=3,
        )

        self.assertNotEqual(
            base,
            build_embedding_version(
                content_hash="hash-b",
                model=MODEL,
                dimensions=3,
            ),
        )
        self.assertNotEqual(
            base,
            build_embedding_version(
                content_hash="hash-a",
                model="text-embedding-3-large",
                dimensions=3,
            ),
        )
        self.assertNotEqual(
            base,
            build_embedding_version(
                content_hash="hash-a",
                model=MODEL,
                dimensions=2,
            ),
        )

    def test_api_failure_keeps_completed_batch_and_retry_only_sends_pending(self):
        chunks = [
            _chunk(0, "first"),
            _chunk(1, "second"),
            _chunk(2, "third"),
        ]
        failing_client = Mock(spec=OpenAIEmbeddingClient)
        failing_client.create_embeddings.side_effect = (
            [_vector(1), _vector(2)],
            EmbeddingAPIError("offline"),
        )

        with self.assertRaises(EmbeddingAPIError):
            self._service(failing_client).embed_chunks(chunks)

        self.assertEqual(self.store.count(), 2)
        retry_client = Mock(spec=OpenAIEmbeddingClient)
        retry_client.create_embeddings.return_value = [_vector(3)]

        result = self._service(retry_client).embed_chunks(chunks)

        self.assertEqual(result.embedded_chunks, 1)
        self.assertEqual(result.skipped_unchanged, 2)
        self.assertEqual(result.api_batches, 1)
        retry_client.create_embeddings.assert_called_once_with(
            ["third"],
            model=MODEL,
            dimensions=DIMENSIONS,
        )
        self.assertEqual(self.store.count(), 3)

    def test_saved_records_are_available_after_store_is_reopened(self):
        client = Mock(spec=OpenAIEmbeddingClient)
        client.create_embeddings.return_value = [_vector(1)]
        chunk = _chunk(0, "persistent")
        self._service(client).embed_chunks([chunk])

        reopened = EmbeddingStore(self.store.db_path)
        records = reopened.list_records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["content"], "persistent")
        self.assertEqual(records[0]["embedding"], _vector(1))


if __name__ == "__main__":
    unittest.main()
