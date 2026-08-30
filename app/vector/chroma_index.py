import hashlib
import re

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb

from chromadb.config import Settings

from app.config import CHROMA_PERSIST_DIRECTORY


DEFAULT_CHROMA_UPSERT_BATCH_SIZE = 1000
DEFAULT_CHROMA_SCAN_PAGE_SIZE = 1000


class ChromaIndexError(RuntimeError):
    """Raised when the regenerable Chroma index cannot be synchronized."""


@dataclass(frozen=True)
class ChromaChunkRecord:
    chunk_id: str
    embedding: list[float]
    document: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ChromaPageSyncResult:
    collection_name: str
    current_chunks: int
    upserted_chunks: int
    deleted_chunks: int


@dataclass(frozen=True)
class IndexedNotionPage:
    notion_page_id: str
    notion_page_key: str
    chunk_ids: tuple[str, ...]


class ChromaIndex:
    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        persistence_path: str | Path = CHROMA_PERSIST_DIRECTORY,
        client: Any | None = None,
        create_if_missing: bool = True,
    ):
        normalized_model = (model or "").strip()

        if not normalized_model:
            raise ChromaIndexError(
                "Chroma CollectionのEmbedding modelが指定されていません。"
            )

        if (
            not isinstance(dimensions, int)
            or isinstance(dimensions, bool)
            or dimensions < 1
        ):
            raise ChromaIndexError(
                "Chroma Collectionのdimensionsは1以上の整数が必要です。"
            )

        self.model = normalized_model
        self.dimensions = dimensions
        self.persistence_path = Path(persistence_path)
        self.collection_name = build_chroma_collection_name(
            model=normalized_model,
            dimensions=dimensions,
        )
        self._closed = False

        try:
            self._client = client or chromadb.PersistentClient(
                path=str(self.persistence_path),
                settings=Settings(anonymized_telemetry=False),
            )
            collection_metadata = {
                "index_source": "notion",
                "embedding_model": normalized_model,
                "embedding_dimensions": dimensions,
            }

            if create_if_missing:
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata=collection_metadata,
                    embedding_function=None,
                )
            else:
                self._collection = self._client.get_collection(
                    name=self.collection_name,
                    embedding_function=None,
                )

            self._validate_collection_metadata(collection_metadata)
            self._upsert_batch_size = min(
                DEFAULT_CHROMA_UPSERT_BATCH_SIZE,
                self._client.get_max_batch_size(),
            )
        except ChromaIndexError:
            raise
        except Exception as error:
            raise ChromaIndexError(
                "Chroma Collectionを初期化できませんでした。"
                f"種別: {type(error).__name__}。"
            ) from None

    def sync_page(
        self,
        *,
        notion_page_id: str,
        records: list[ChromaChunkRecord],
    ) -> ChromaPageSyncResult:
        page_key = canonical_notion_page_id(notion_page_id)
        existing_ids = set(self.get_page_chunk_ids(notion_page_id))
        current_ids = set()

        for record in records:
            self._validate_record(record, page_key=page_key)

            if record.chunk_id in current_ids:
                raise ChromaIndexError(
                    f"同じChunk IDが重複しています: {record.chunk_id}"
                )

            current_ids.add(record.chunk_id)

        for offset in range(0, len(records), self._upsert_batch_size):
            batch = records[offset:offset + self._upsert_batch_size]

            try:
                self._collection.upsert(
                    ids=[record.chunk_id for record in batch],
                    embeddings=[record.embedding for record in batch],
                    documents=[record.document for record in batch],
                    metadatas=[record.metadata for record in batch],
                )
            except Exception as error:
                raise ChromaIndexError(
                    "ChromaへのChunk Upsertに失敗しました。"
                    f"種別: {type(error).__name__}。"
                ) from None

        stale_ids = sorted(existing_ids.difference(current_ids))

        if stale_ids:
            try:
                self._collection.delete(ids=stale_ids)
            except Exception as error:
                raise ChromaIndexError(
                    "Chromaの古いChunk削除に失敗しました。"
                    f"種別: {type(error).__name__}。"
                ) from None

        return ChromaPageSyncResult(
            collection_name=self.collection_name,
            current_chunks=len(current_ids),
            upserted_chunks=len(records),
            deleted_chunks=len(stale_ids),
        )

    def get_page_chunk_ids(self, notion_page_id: str) -> tuple[str, ...]:
        page_key = canonical_notion_page_id(notion_page_id)

        try:
            result = self._collection.get(
                where={"notion_page_key": page_key},
                include=[],
            )
        except Exception as error:
            raise ChromaIndexError(
                "ChromaからPage Chunkを取得できませんでした。"
                f"種別: {type(error).__name__}。"
            ) from None

        ids = result.get("ids")

        if not isinstance(ids, list) or any(
            not isinstance(chunk_id, str)
            for chunk_id in ids
        ):
            raise ChromaIndexError(
                "ChromaのPage Chunk IDレスポンスが不正です。"
            )

        return tuple(sorted(ids))

    def list_indexed_pages(self) -> list[IndexedNotionPage]:
        pages: dict[str, dict[str, Any]] = {}
        offset = 0

        while True:
            try:
                result = self._collection.get(
                    limit=DEFAULT_CHROMA_SCAN_PAGE_SIZE,
                    offset=offset,
                    include=["metadatas"],
                )
            except Exception as error:
                raise ChromaIndexError(
                    "ChromaのIndex Page一覧を取得できませんでした。"
                    f"種別: {type(error).__name__}。"
                ) from None

            ids = result.get("ids")
            metadatas = result.get("metadatas")

            if not isinstance(ids, list) or not isinstance(metadatas, list):
                raise ChromaIndexError(
                    "ChromaのIndex Page一覧レスポンスが不正です。"
                )

            if len(ids) != len(metadatas):
                raise ChromaIndexError(
                    "ChromaのChunk IDとMetadata件数が一致しません。"
                )

            for chunk_id, metadata in zip(ids, metadatas, strict=True):
                if not isinstance(chunk_id, str) or not isinstance(
                    metadata,
                    dict,
                ):
                    raise ChromaIndexError(
                        "ChromaのChunk Metadataが不正です。"
                    )

                page_id = metadata.get("notion_page_id")
                page_key = metadata.get("notion_page_key")

                if (
                    not isinstance(page_id, str)
                    or not page_id.strip()
                    or not isinstance(page_key, str)
                    or page_key != canonical_notion_page_id(page_id)
                ):
                    raise ChromaIndexError(
                        "ChromaのNotion Page Metadataが不正です。"
                    )

                page = pages.setdefault(
                    page_key,
                    {
                        "notion_page_id": page_id,
                        "chunk_ids": [],
                    },
                )
                page["chunk_ids"].append(chunk_id)

            if len(ids) < DEFAULT_CHROMA_SCAN_PAGE_SIZE:
                break

            offset += len(ids)

        return [
            IndexedNotionPage(
                notion_page_id=page["notion_page_id"],
                notion_page_key=page_key,
                chunk_ids=tuple(sorted(page["chunk_ids"])),
            )
            for page_key, page in sorted(pages.items())
        ]

    def get_page_records(self, notion_page_id: str) -> dict[str, Any]:
        page_key = canonical_notion_page_id(notion_page_id)

        try:
            return dict(
                self._collection.get(
                    where={"notion_page_key": page_key},
                    include=["embeddings", "documents", "metadatas"],
                )
            )
        except Exception as error:
            raise ChromaIndexError(
                "ChromaからPage Recordを取得できませんでした。"
                f"種別: {type(error).__name__}。"
            ) from None

    def count(self) -> int:
        try:
            return int(self._collection.count())
        except Exception as error:
            raise ChromaIndexError(
                "ChromaのChunk件数を取得できませんでした。"
                f"種別: {type(error).__name__}。"
            ) from None

    def close(self) -> None:
        if self._closed:
            return

        try:
            self._client.close()
        except Exception as error:
            raise ChromaIndexError(
                "Chroma Clientを終了できませんでした。"
                f"種別: {type(error).__name__}。"
            ) from None

        self._closed = True

    def _validate_collection_metadata(
        self,
        expected: dict[str, Any],
    ) -> None:
        metadata = self._collection.metadata

        if not isinstance(metadata, dict) or any(
            metadata.get(key) != value
            for key, value in expected.items()
        ):
            raise ChromaIndexError(
                "Chroma Collectionのmodelまたはdimensionsが一致しません。"
            )

    def _validate_record(
        self,
        record: ChromaChunkRecord,
        *,
        page_key: str,
    ) -> None:
        if not isinstance(record.chunk_id, str) or not record.chunk_id.strip():
            raise ChromaIndexError("Chromaへ保存するChunk IDが不正です。")

        if not isinstance(record.document, str) or not record.document.strip():
            raise ChromaIndexError("Chromaへ空のChunkは保存できません。")

        if (
            not isinstance(record.embedding, list)
            or len(record.embedding) != self.dimensions
        ):
            raise ChromaIndexError(
                "Chromaへ保存するEmbeddingの次元数が一致しません。"
            )

        if not isinstance(record.metadata, dict):
            raise ChromaIndexError("Chromaへ保存するMetadataが不正です。")

        if record.metadata.get("notion_page_key") != page_key:
            raise ChromaIndexError(
                "Chunk MetadataのNotion Page IDが同期対象と一致しません。"
            )

        if (
            record.metadata.get("embedding_model") != self.model
            or record.metadata.get("embedding_dimensions") != self.dimensions
        ):
            raise ChromaIndexError(
                "Chunk MetadataのEmbedding設定がCollectionと一致しません。"
            )


def build_chroma_collection_name(*, model: str, dimensions: int) -> str:
    normalized_model = (model or "").strip().lower()

    if not normalized_model or dimensions < 1:
        raise ChromaIndexError("Chroma Collection名の入力が不正です。")

    slug = re.sub(r"[^a-z0-9_-]+", "-", normalized_model).strip("-_")
    slug = (slug or "embedding-model")[:48].rstrip("-_")
    identity = f"{normalized_model}\0{dimensions}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"jarvis-{slug}-{dimensions}-{digest}"


def canonical_notion_page_id(value: str) -> str:
    normalized = (value or "").strip().replace("-", "").lower()

    if not normalized:
        raise ChromaIndexError("Notion Page IDが指定されていません。")

    return normalized
