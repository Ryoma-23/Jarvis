from dataclasses import dataclass

from app.chunking.notion_chunker import (
    NotionChunk,
    NotionPageChunkingService,
)
from app.embeddings.embedding_service import (
    EmbeddingRunResult,
    EmbeddingService,
    build_embedding_version,
)
from app.embeddings.embedding_store import EmbeddingStore
from app.integrations.notion_client import (
    NotionClient,
    NotionResourceNotFoundError,
    NotionResponseError,
)
from app.vector.chroma_index import (
    ChromaChunkRecord,
    ChromaIndex,
    ChromaIndexError,
    ChromaPageSyncResult,
    IndexedNotionPage,
    canonical_notion_page_id,
)


@dataclass(frozen=True)
class NotionChromaSyncResult:
    notion_page_id: str
    chunk_count: int
    embedding_result: EmbeddingRunResult
    chroma_result: ChromaPageSyncResult


@dataclass(frozen=True)
class MissingIndexedNotionPage:
    notion_page_id: str
    chunk_ids: tuple[str, ...]
    reason: str


class NotionChromaSyncService:
    def __init__(
        self,
        *,
        chunking_service: NotionPageChunkingService,
        embedding_service: EmbeddingService,
        embedding_store: EmbeddingStore,
        chroma_index: ChromaIndex,
        model: str,
        dimensions: int,
    ):
        self._chunking_service = chunking_service
        self._embedding_service = embedding_service
        self._embedding_store = embedding_store
        self._chroma_index = chroma_index
        self._model = model
        self._dimensions = dimensions

    def sync_page(self, notion_page_id: str) -> NotionChromaSyncResult:
        chunks = self._chunking_service.chunk_page(notion_page_id)
        embedding_result = self._embedding_service.embed_chunks(chunks)
        chroma_records = [
            self._chroma_record(chunk)
            for chunk in chunks
            if chunk.content.strip()
        ]
        chroma_result = self._chroma_index.sync_page(
            notion_page_id=notion_page_id,
            records=chroma_records,
        )
        return NotionChromaSyncResult(
            notion_page_id=notion_page_id,
            chunk_count=len(chroma_records),
            embedding_result=embedding_result,
            chroma_result=chroma_result,
        )

    def _chroma_record(self, chunk: NotionChunk) -> ChromaChunkRecord:
        embedding_version = build_embedding_version(
            content_hash=chunk.content_hash,
            model=self._model,
            dimensions=self._dimensions,
        )
        stored = self._embedding_store.get(
            chunk_id=chunk.chunk_id,
            embedding_version=embedding_version,
        )

        if stored is None:
            raise ChromaIndexError(
                f"Chunk {chunk.chunk_id} のEmbeddingが保存されていません。"
            )

        if (
            stored.get("content_hash") != chunk.content_hash
            or stored.get("model") != self._model
            or stored.get("dimensions") != self._dimensions
            or stored.get("content") != chunk.content
        ):
            raise ChromaIndexError(
                f"Chunk {chunk.chunk_id} のEmbedding versionが一致しません。"
            )

        embedding = stored.get("embedding")

        if not isinstance(embedding, list):
            raise ChromaIndexError(
                f"Chunk {chunk.chunk_id} のEmbedding vectorが不正です。"
            )

        metadata = {
            "notion_page_id": chunk.notion_page_id,
            "notion_page_key": canonical_notion_page_id(
                chunk.notion_page_id
            ),
            "block_id": chunk.block_id,
            "title": chunk.title,
            "chunk_index": chunk.chunk_index,
            "content_hash": chunk.content_hash,
            "last_edited_time": chunk.last_edited_time,
            "source_type": chunk.source_type,
            "notion_url": chunk.notion_url,
            "embedding_version": embedding_version,
            "embedding_model": self._model,
            "embedding_dimensions": self._dimensions,
            "block_ids": list(chunk.block_ids),
        }

        if chunk.heading_path:
            metadata["heading_path"] = list(chunk.heading_path)

        return ChromaChunkRecord(
            chunk_id=chunk.chunk_id,
            embedding=embedding,
            document=chunk.content,
            metadata=metadata,
        )


class ChromaNotionPageAuditor:
    def __init__(
        self,
        *,
        notion_client: NotionClient,
        chroma_index: ChromaIndex,
    ):
        self._notion_client = notion_client
        self._chroma_index = chroma_index

    def find_missing_pages(self) -> list[MissingIndexedNotionPage]:
        missing = []

        for indexed_page in self._chroma_index.list_indexed_pages():
            status = self._page_status(indexed_page)

            if status is not None:
                missing.append(status)

        return missing

    def _page_status(
        self,
        indexed_page: IndexedNotionPage,
    ) -> MissingIndexedNotionPage | None:
        try:
            page = self._notion_client.retrieve_page(
                indexed_page.notion_page_id
            )
        except NotionResourceNotFoundError:
            return MissingIndexedNotionPage(
                notion_page_id=indexed_page.notion_page_id,
                chunk_ids=indexed_page.chunk_ids,
                reason="not_found",
            )

        retrieved_page_id = page.get("id")

        if (
            not isinstance(retrieved_page_id, str)
            or canonical_notion_page_id(retrieved_page_id)
            != indexed_page.notion_page_key
        ):
            raise NotionResponseError(
                "Chroma監査で取得したNotion Page IDが一致しません。"
            )

        if page.get("in_trash") is True or page.get("archived") is True:
            return MissingIndexedNotionPage(
                notion_page_id=indexed_page.notion_page_id,
                chunk_ids=indexed_page.chunk_ids,
                reason="in_trash",
            )

        return None
