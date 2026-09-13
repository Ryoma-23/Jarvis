from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app import config
from app.chunking.notion_chunker import NotionPageChunkingService
from app.chunking.notion_memo_chunker import (
    NOTION_MEMO_SOURCE_TYPE,
    NotionMemoChunker,
)
from app.embeddings.embedding_service import EmbeddingService
from app.embeddings.embedding_store import EmbeddingStore
from app.integrations.notion_client import (
    NotionClient,
    NotionConfigurationError,
    NotionResponseError,
)
from app.integrations.notion_memo_reader import NotionMemoReader
from app.integrations.notion_resources import resolve_notes_data_source_id
from app.integrations.openai_embedding_client import OpenAIEmbeddingClient
from app.knowledge_sync.lock import KnowledgeSyncLock
from app.knowledge_sync.registry import canonical_notion_id
from app.knowledge_sync.retry import run_with_sync_retry
from app.knowledge_sync.state import KnowledgeSyncStateStore
from app.vector.chroma_index import ChromaIndex
from app.vector.notion_chroma_sync import NotionChromaSyncService


DEFAULT_ON_WRITE_LOCK_WAIT_SECONDS = 15.0


@dataclass(frozen=True)
class MemoKnowledgeIndexResult:
    notion_page_id: str
    chunk_count: int
    embedded_chunks: int
    skipped_unchanged: int
    deleted_chunks: int


class MemoKnowledgeIndexer:
    def __init__(
        self,
        *,
        reader: NotionMemoReader,
        chunker: NotionMemoChunker,
        chroma_sync_service: NotionChromaSyncService,
        chroma_index: ChromaIndex,
        state_store: KnowledgeSyncStateStore,
        embedding_model: str,
        embedding_dimensions: int,
        retry_count: int,
        sleeper: Callable[[float], None] | None = None,
    ):
        self._reader = reader
        self._chunker = chunker
        self._chroma_sync_service = chroma_sync_service
        self._chroma_index = chroma_index
        self._state_store = state_store
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._retry_count = retry_count
        self._sleeper = sleeper

    def sync_page(self, page_id: str) -> MemoKnowledgeIndexResult:
        normalized_page_id = (page_id or "").strip()

        if not normalized_page_id:
            raise NotionConfigurationError(
                "即時RAG同期のNotion Page IDが指定されていません。"
            )

        memo = self._with_retry(
            lambda: self._reader.get_by_page_id_for_indexing(
                normalized_page_id
            )
        )
        retrieved_page_id = _required_memo_text(
            memo,
            "notion_page_id",
        )

        if (
            canonical_notion_id(retrieved_page_id)
            != canonical_notion_id(normalized_page_id)
        ):
            raise NotionResponseError(
                "即時RAG同期で取得したNotion Page IDが一致しません。"
            )

        last_edited_time = _required_memo_text(
            memo,
            "notion_last_edited_time",
        )
        chunks = self._chunker.chunk(memo)
        sync_result = self._with_retry(
            lambda: self._chroma_sync_service.sync_chunks(
                notion_page_id=retrieved_page_id,
                chunks=chunks,
            )
        )
        state = self._state_store.load(
            collection_name=self._chroma_index.collection_name,
            embedding_model=self._embedding_model,
            embedding_dimensions=self._embedding_dimensions,
        )
        state.record(
            page_id=retrieved_page_id,
            source_type=NOTION_MEMO_SOURCE_TYPE,
            last_edited_time=last_edited_time,
            chunk_count=sync_result.chunk_count,
            synced_at=datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        )
        self._state_store.save(state)
        return MemoKnowledgeIndexResult(
            notion_page_id=retrieved_page_id,
            chunk_count=sync_result.chunk_count,
            embedded_chunks=(
                sync_result.embedding_result.embedded_chunks
            ),
            skipped_unchanged=(
                sync_result.embedding_result.skipped_unchanged
            ),
            deleted_chunks=sync_result.chroma_result.deleted_chunks,
        )

    def _with_retry(self, operation):
        arguments = {"attempts": self._retry_count}

        if self._sleeper is not None:
            arguments["sleeper"] = self._sleeper

        return run_with_sync_retry(operation, **arguments)


def sync_notion_memo_page_on_write(
    page_id: str,
    *,
    lock_wait_seconds: float = DEFAULT_ON_WRITE_LOCK_WAIT_SECONDS,
) -> MemoKnowledgeIndexResult:
    data_source_id = resolve_notes_data_source_id()

    if data_source_id is None:
        raise NotionConfigurationError(
            "Notes用Data Source IDが設定されていません。"
        )

    lock = KnowledgeSyncLock()
    lock.acquire(timeout_seconds=lock_wait_seconds)
    chroma_index = None

    try:
        notion_client = NotionClient(
            api_token=config.NOTION_API_TOKEN,
            api_version=config.NOTION_API_VERSION,
        )
        reader = NotionMemoReader(
            client=notion_client,
            data_source_id=data_source_id,
        )
        embedding_store = EmbeddingStore(config.EMBEDDINGS_DB_FILE)
        embedding_service = EmbeddingService(
            client=OpenAIEmbeddingClient(api_key=config.OPENAI_API_KEY),
            store=embedding_store,
            model=config.OPENAI_EMBEDDING_MODEL,
            dimensions=config.OPENAI_EMBEDDING_DIMENSIONS,
            batch_size=config.OPENAI_EMBEDDING_BATCH_SIZE,
        )
        chroma_index = ChromaIndex(
            model=config.OPENAI_EMBEDDING_MODEL,
            dimensions=config.OPENAI_EMBEDDING_DIMENSIONS,
            persistence_path=config.CHROMA_PERSIST_DIRECTORY,
        )
        chroma_sync_service = NotionChromaSyncService(
            chunking_service=NotionPageChunkingService(
                client=notion_client
            ),
            embedding_service=embedding_service,
            embedding_store=embedding_store,
            chroma_index=chroma_index,
            model=config.OPENAI_EMBEDDING_MODEL,
            dimensions=config.OPENAI_EMBEDDING_DIMENSIONS,
        )
        return MemoKnowledgeIndexer(
            reader=reader,
            chunker=NotionMemoChunker(),
            chroma_sync_service=chroma_sync_service,
            chroma_index=chroma_index,
            state_store=KnowledgeSyncStateStore(),
            embedding_model=config.OPENAI_EMBEDDING_MODEL,
            embedding_dimensions=config.OPENAI_EMBEDDING_DIMENSIONS,
            retry_count=config.NOTION_KNOWLEDGE_SYNC_RETRY_COUNT,
        ).sync_page(page_id)
    finally:
        try:
            if chroma_index is not None:
                chroma_index.close()
        finally:
            lock.release()


def _required_memo_text(memo: dict, key: str) -> str:
    value = memo.get(key)

    if not isinstance(value, str) or not value.strip():
        raise NotionResponseError(
            f"即時RAG同期でMemoの{key}を取得できませんでした。"
        )

    return value.strip()
