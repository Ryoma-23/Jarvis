import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

from app.integrations.notion_client import (
    NotionClient,
    NotionResourceNotFoundError,
)
from app.vector.chroma_index import (
    ChromaChunkRecord,
    ChromaIndex,
    ChromaIndexError,
    build_chroma_collection_name,
    canonical_notion_page_id,
)
from app.vector.notion_chroma_sync import ChromaNotionPageAuditor


PAGE_ID = "11111111-2222-3333-4444-555555555555"
OTHER_PAGE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TRASH_PAGE_ID = "99999999-8888-7777-6666-555555555555"
MODEL = "text-embedding-3-small"
DIMENSIONS = 3


def _record(
    chunk_id,
    document,
    vector,
    *,
    page_id=PAGE_ID,
    model=MODEL,
    dimensions=DIMENSIONS,
):
    return ChromaChunkRecord(
        chunk_id=chunk_id,
        embedding=vector,
        document=document,
        metadata={
            "notion_page_id": page_id,
            "notion_page_key": canonical_notion_page_id(page_id),
            "block_id": f"block-{chunk_id}",
            "title": "Chroma Test",
            "chunk_index": 0,
            "content_hash": f"hash-{chunk_id}",
            "last_edited_time": "2026-08-30T00:00:00+00:00",
            "source_type": "notion_page",
            "notion_url": "https://www.notion.so/chroma-test",
            "embedding_version": f"embedding-{chunk_id}",
            "embedding_model": model,
            "embedding_dimensions": dimensions,
            "heading_path": ["Test"],
            "block_ids": [f"block-{chunk_id}"],
        },
    )


class ChromaIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        )
        self.path = Path(self.temporary_directory.name) / "chroma"
        self.indexes = []

    def tearDown(self):
        for index in reversed(self.indexes):
            index.close()

        self.temporary_directory.cleanup()

    def _index(self, *, model=MODEL, dimensions=DIMENSIONS):
        index = ChromaIndex(
            model=model,
            dimensions=dimensions,
            persistence_path=self.path,
        )
        self.indexes.append(index)
        return index

    def test_persists_records_and_separates_model_dimension_collections(self):
        small = self._index()
        result = small.sync_page(
            notion_page_id=PAGE_ID,
            records=[
                _record("chunk-a", "First", [0.1, 0.2, 0.3]),
                _record("chunk-b", "Second", [0.4, 0.5, 0.6]),
            ],
        )

        self.assertEqual(result.upserted_chunks, 2)
        self.assertEqual(small.count(), 2)
        reopened = self._index()
        self.assertEqual(reopened.count(), 2)
        records = reopened.get_page_records(PAGE_ID)
        self.assertEqual(set(records["ids"]), {"chunk-a", "chunk-b"})
        metadata = records["metadatas"][0]
        self.assertEqual(metadata["notion_page_id"], PAGE_ID)
        self.assertEqual(metadata["title"], "Chroma Test")
        self.assertEqual(
            metadata["notion_url"],
            "https://www.notion.so/chroma-test",
        )

        large = self._index(model="text-embedding-3-large")
        two_dimensions = self._index(dimensions=2)
        self.assertNotEqual(small.collection_name, large.collection_name)
        self.assertNotEqual(
            small.collection_name,
            two_dimensions.collection_name,
        )
        self.assertEqual(large.count(), 0)
        self.assertEqual(two_dimensions.count(), 0)

    def test_resync_upserts_current_ids_then_deletes_stale_ids(self):
        index = self._index()
        index.sync_page(
            notion_page_id=PAGE_ID,
            records=[
                _record("chunk-a", "Old first", [0.1, 0.2, 0.3]),
                _record("chunk-b", "Removed", [0.4, 0.5, 0.6]),
            ],
        )

        result = index.sync_page(
            notion_page_id=PAGE_ID,
            records=[
                _record("chunk-a", "Updated first", [0.7, 0.8, 0.9]),
                _record("chunk-c", "Added", [0.2, 0.3, 0.4]),
            ],
        )

        self.assertEqual(result.deleted_chunks, 1)
        self.assertEqual(
            index.get_page_chunk_ids(PAGE_ID),
            ("chunk-a", "chunk-c"),
        )
        records = index.get_page_records(PAGE_ID)
        documents = dict(zip(records["ids"], records["documents"], strict=True))
        self.assertEqual(documents["chunk-a"], "Updated first")

    def test_empty_page_sync_deletes_all_previous_page_chunks_only(self):
        index = self._index()
        index.sync_page(
            notion_page_id=PAGE_ID,
            records=[_record("chunk-a", "First", [0.1, 0.2, 0.3])],
        )
        index.sync_page(
            notion_page_id=OTHER_PAGE_ID,
            records=[
                _record(
                    "other-chunk",
                    "Other",
                    [0.4, 0.5, 0.6],
                    page_id=OTHER_PAGE_ID,
                )
            ],
        )

        result = index.sync_page(notion_page_id=PAGE_ID, records=[])

        self.assertEqual(result.deleted_chunks, 1)
        self.assertEqual(index.get_page_chunk_ids(PAGE_ID), ())
        self.assertEqual(
            index.get_page_chunk_ids(OTHER_PAGE_ID),
            ("other-chunk",),
        )

    def test_rejects_wrong_vector_dimension_before_upsert(self):
        index = self._index()

        with self.assertRaisesRegex(ChromaIndexError, "次元数"):
            index.sync_page(
                notion_page_id=PAGE_ID,
                records=[_record("chunk-a", "First", [0.1, 0.2])],
            )

        self.assertEqual(index.count(), 0)

    def test_collection_name_is_deterministic_for_model_and_dimensions(self):
        first = build_chroma_collection_name(
            model=MODEL,
            dimensions=DIMENSIONS,
        )
        second = build_chroma_collection_name(
            model=MODEL,
            dimensions=DIMENSIONS,
        )

        self.assertEqual(first, second)
        self.assertNotEqual(
            first,
            build_chroma_collection_name(model=MODEL, dimensions=2),
        )


class ChromaNotionPageAuditorTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        )
        self.index = ChromaIndex(
            model=MODEL,
            dimensions=DIMENSIONS,
            persistence_path=(
                Path(self.temporary_directory.name) / "chroma"
            ),
        )
        self.index.sync_page(
            notion_page_id=PAGE_ID,
            records=[_record("active", "Active", [0.1, 0.2, 0.3])],
        )
        self.index.sync_page(
            notion_page_id=OTHER_PAGE_ID,
            records=[
                _record(
                    "missing",
                    "Missing",
                    [0.4, 0.5, 0.6],
                    page_id=OTHER_PAGE_ID,
                )
            ],
        )
        self.index.sync_page(
            notion_page_id=TRASH_PAGE_ID,
            records=[
                _record(
                    "trash",
                    "Trash",
                    [0.7, 0.8, 0.9],
                    page_id=TRASH_PAGE_ID,
                )
            ],
        )

    def tearDown(self):
        self.index.close()
        self.temporary_directory.cleanup()

    def test_detects_not_found_and_trashed_pages_without_deleting(self):
        notion_client = Mock(spec=NotionClient)

        def retrieve(page_id):
            if page_id == PAGE_ID:
                return {"id": PAGE_ID, "in_trash": False}

            if page_id == OTHER_PAGE_ID:
                raise NotionResourceNotFoundError(
                    "not found",
                    status_code=404,
                )

            return {"id": TRASH_PAGE_ID, "in_trash": True}

        notion_client.retrieve_page.side_effect = retrieve

        with patch(
            "app.vector.chroma_index.DEFAULT_CHROMA_SCAN_PAGE_SIZE",
            1,
        ):
            missing = ChromaNotionPageAuditor(
                notion_client=notion_client,
                chroma_index=self.index,
            ).find_missing_pages()

        self.assertEqual(
            {(page.notion_page_id, page.reason) for page in missing},
            {
                (OTHER_PAGE_ID, "not_found"),
                (TRASH_PAGE_ID, "in_trash"),
            },
        )
        self.assertEqual(self.index.count(), 3)


if __name__ == "__main__":
    unittest.main()
