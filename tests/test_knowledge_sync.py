import json
import tempfile
import time
import unittest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.chunking.notion_chunker import NotionPageChunkingService
from app.chunking.notion_memo_chunker import NotionMemoChunker
from app.integrations.notion_client import (
    NotionClient,
    NotionConnectionError,
    NotionResourceNotFoundError,
)
from app.integrations.notion_memo_reader import NotionMemoReader
from app.knowledge_sync.lock import (
    KnowledgeSyncAlreadyRunningError,
    KnowledgeSyncLock,
)
from app.knowledge_sync.registry import (
    KnowledgePageSource,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryError,
    KnowledgeSourceRegistryStore,
)
from app.knowledge_sync.service import NotionKnowledgeSyncService
from app.knowledge_sync.state import (
    KnowledgeSyncState,
    KnowledgeSyncStateStore,
)
from app.vector.chroma_index import ChromaIndex, IndexedNotionPage
from app.vector.notion_chroma_sync import NotionChromaSyncService


PAGE_ID = "11111111-2222-3333-4444-555555555555"
OTHER_PAGE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
EDITED_AT = "2026-09-07T00:00:00.000Z"


class KnowledgeSourceRegistryTests(unittest.TestCase):
    def test_missing_registry_is_non_authoritative_and_notes_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = KnowledgeSourceRegistryStore(
                Path(directory) / "sources.json"
            ).load()

        self.assertFalse(registry.authoritative)
        self.assertTrue(registry.include_notes)
        self.assertEqual(registry.pages, ())

    def test_add_save_load_remove_and_notes_setting(self):
        with tempfile.TemporaryDirectory() as directory:
            store = KnowledgeSourceRegistryStore(
                Path(directory) / "sources.json"
            )
            registry = (
                store.load()
                .add_page(PAGE_ID, label="開発記録")
                .add_page(PAGE_ID.replace("-", ""), label="更新後")
                .with_notes(False)
            )
            store.save(registry)
            loaded = store.load()

            self.assertTrue(loaded.authoritative)
            self.assertFalse(loaded.include_notes)
            self.assertEqual(len(loaded.pages), 1)
            self.assertEqual(loaded.pages[0].label, "更新後")
            store.save(loaded.add_page(PAGE_ID))
            self.assertEqual(store.load().pages[0].label, "更新後")
            store.save(loaded.remove_page(PAGE_ID))
            self.assertEqual(store.load().pages, ())

    def test_invalid_registry_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps({"version": 99}), encoding="utf-8")

            with self.assertRaises(KnowledgeSourceRegistryError):
                KnowledgeSourceRegistryStore(path).load()


class KnowledgeSyncLockTests(unittest.TestCase):
    def test_lock_prevents_overlap_and_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sync.lock"
            first = KnowledgeSyncLock(path)
            first.acquire()

            with self.assertRaises(KnowledgeSyncAlreadyRunningError):
                KnowledgeSyncLock(path).acquire()

            first.release()
            with KnowledgeSyncLock(path):
                self.assertTrue(path.exists())

            self.assertFalse(path.exists())

    def test_stale_lock_is_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sync.lock"
            path.write_text(
                json.dumps({"created_at": time.time() - 100}),
                encoding="utf-8",
            )

            with KnowledgeSyncLock(path, stale_after_seconds=10):
                self.assertTrue(path.exists())


class NotionKnowledgeSyncServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_store = KnowledgeSyncStateStore(
            Path(self.temporary_directory.name) / "state.json"
        )
        self.page_service = Mock(spec=NotionPageChunkingService)
        self.memo_reader = Mock(spec=NotionMemoReader)
        self.memo_chunker = Mock(spec=NotionMemoChunker)
        self.index = Mock(spec=ChromaIndex)
        self.index.collection_name = "test-collection"
        self.index.list_indexed_pages.return_value = []
        self.sync_service = Mock(spec=NotionChromaSyncService)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def service(
        self,
        registry,
        *,
        memo_reader=None,
        sync_service=None,
        retry_count=3,
        sleeper=None,
    ):
        arguments = {
            "registry": registry,
            "page_chunking_service": self.page_service,
            "memo_chunker": self.memo_chunker,
            "memo_reader": memo_reader,
            "chroma_index": self.index,
            "state_store": self.state_store,
            "embedding_model": "model",
            "embedding_dimensions": 3,
            "chroma_sync_service": sync_service,
            "retry_count": retry_count,
        }

        if sleeper is not None:
            arguments["sleeper"] = sleeper

        return NotionKnowledgeSyncService(**arguments)

    def test_existing_metadata_skips_block_fetch_and_embedding(self):
        registry = KnowledgeSourceRegistry(
            pages=(KnowledgePageSource(PAGE_ID),),
            include_notes=False,
            authoritative=True,
        )
        self.index.list_indexed_pages.return_value = [
            _indexed(PAGE_ID, source_type="notion_page")
        ]
        self.page_service.retrieve_page.return_value = _page(PAGE_ID)

        summary = self.service(registry).run(dry_run=True)

        self.assertEqual(summary.unchanged_pages, 1)
        self.page_service.chunk_retrieved_page.assert_not_called()

    def test_changed_page_syncs_and_persists_incremental_state(self):
        registry = KnowledgeSourceRegistry(
            pages=(KnowledgePageSource(PAGE_ID),),
            include_notes=False,
            authoritative=True,
        )
        chunks = [Mock(), Mock()]
        self.page_service.retrieve_page.return_value = _page(PAGE_ID)
        self.page_service.chunk_retrieved_page.return_value = chunks
        self.sync_service.sync_chunks.return_value = _sync_result(2)

        summary = self.service(
            registry,
            sync_service=self.sync_service,
        ).run(dry_run=False)

        self.assertEqual(summary.changed_pages, 1)
        state = self.state_store.load(
            collection_name="test-collection",
            embedding_model="model",
            embedding_dimensions=3,
        )
        record = state.pages[PAGE_ID.replace("-", "")]
        self.assertEqual(record["last_edited_time"], EDITED_AT)
        self.assertEqual(record["chunk_count"], 2)

    def test_unchanged_memo_does_not_fetch_full_content(self):
        registry = KnowledgeSourceRegistry(
            include_notes=True,
            authoritative=True,
        )
        memo = _memo(PAGE_ID)
        self.memo_reader.list_notes.return_value = [memo]
        self.index.list_indexed_pages.return_value = [
            _indexed(PAGE_ID, source_type="notion_memo")
        ]

        summary = self.service(
            registry,
            memo_reader=self.memo_reader,
        ).run(dry_run=True)

        self.assertEqual(summary.unchanged_pages, 1)
        self.memo_reader.hydrate_content_for_indexing.assert_not_called()

    def test_changed_memo_fetches_full_content_before_sync(self):
        registry = KnowledgeSourceRegistry(
            include_notes=True,
            authoritative=True,
        )
        memo = _memo(PAGE_ID)
        hydrated = dict(memo, content="完全なContent")
        chunks = [Mock()]
        self.memo_reader.list_notes.return_value = [memo]
        self.memo_reader.hydrate_content_for_indexing.return_value = hydrated
        self.memo_chunker.chunk.return_value = chunks
        self.sync_service.sync_chunks.return_value = _sync_result(1)

        summary = self.service(
            registry,
            memo_reader=self.memo_reader,
            sync_service=self.sync_service,
        ).run(dry_run=False)

        self.assertEqual(summary.changed_pages, 1)
        self.memo_chunker.chunk.assert_called_once_with(hydrated)

    def test_authoritative_registry_removes_unregistered_normal_page(self):
        registry = KnowledgeSourceRegistry(
            include_notes=False,
            authoritative=True,
        )
        self.index.list_indexed_pages.return_value = [
            _indexed(PAGE_ID, source_type="notion_page")
        ]
        self.index.delete_page.return_value = 1

        summary = self.service(
            registry,
            sync_service=self.sync_service,
        ).run(dry_run=False)

        self.assertEqual(summary.removed_pages, 1)
        self.index.delete_page.assert_called_once_with(PAGE_ID)

    def test_removed_memo_is_deleted_only_after_successful_query(self):
        registry = KnowledgeSourceRegistry(
            include_notes=True,
            authoritative=True,
        )
        self.memo_reader.list_notes.return_value = []
        self.index.list_indexed_pages.return_value = [
            _indexed(PAGE_ID, source_type="notion_memo")
        ]
        self.index.delete_page.return_value = 1

        summary = self.service(
            registry,
            memo_reader=self.memo_reader,
            sync_service=self.sync_service,
        ).run(dry_run=False)

        self.assertEqual(summary.actions[0].reason, "source_removed")
        self.index.delete_page.assert_called_once_with(PAGE_ID)

    def test_not_found_registered_page_removes_stale_chunks(self):
        registry = KnowledgeSourceRegistry(
            pages=(KnowledgePageSource(PAGE_ID),),
            include_notes=False,
            authoritative=True,
        )
        self.index.list_indexed_pages.return_value = [
            _indexed(PAGE_ID, source_type="notion_page")
        ]
        self.page_service.retrieve_page.side_effect = (
            NotionResourceNotFoundError("not found", status_code=404)
        )
        self.index.delete_page.return_value = 1

        summary = self.service(
            registry,
            sync_service=self.sync_service,
        ).run(dry_run=False)

        self.assertEqual(summary.actions[0].status, "deleted")
        self.assertEqual(summary.actions[0].reason, "not_found")

    def test_transient_connection_error_is_retried(self):
        registry = KnowledgeSourceRegistry(
            pages=(KnowledgePageSource(PAGE_ID),),
            include_notes=False,
            authoritative=True,
        )
        self.page_service.retrieve_page.side_effect = [
            NotionConnectionError("temporary"),
            _page(PAGE_ID),
        ]
        self.page_service.chunk_retrieved_page.return_value = []
        sleeper = Mock()

        summary = self.service(
            registry,
            retry_count=2,
            sleeper=sleeper,
        ).run(dry_run=True)

        self.assertEqual(summary.changed_pages, 1)
        self.assertEqual(self.page_service.retrieve_page.call_count, 2)
        sleeper.assert_called_once_with(1.0)


def _page(page_id):
    return {
        "id": page_id,
        "last_edited_time": EDITED_AT,
        "archived": False,
        "in_trash": False,
    }


def _memo(page_id):
    return {
        "id": 1,
        "notion_page_id": page_id,
        "notion_last_edited_time": EDITED_AT,
        "notion_content_property_id": "content-id",
    }


def _indexed(page_id, *, source_type):
    return IndexedNotionPage(
        notion_page_id=page_id,
        notion_page_key=page_id.replace("-", ""),
        chunk_ids=("chunk-1",),
        source_types=(source_type,),
        last_edited_times=(EDITED_AT,),
    )


def _sync_result(chunk_count):
    return SimpleNamespace(
        chunk_count=chunk_count,
        embedding_result=SimpleNamespace(
            embedded_chunks=chunk_count,
            skipped_unchanged=0,
        ),
        chroma_result=SimpleNamespace(deleted_chunks=0),
    )


if __name__ == "__main__":
    unittest.main()
