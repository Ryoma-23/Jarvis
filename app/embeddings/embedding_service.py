import hashlib

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from app.chunking.notion_chunker import NotionChunk
from app.embeddings.embedding_store import EmbeddingStore
from app.integrations.openai_embedding_client import (
    MAX_EMBEDDING_INPUTS,
    EmbeddingConfigurationError,
    OpenAIEmbeddingClient,
)


@dataclass(frozen=True)
class EmbeddingRunResult:
    total_chunks: int
    embedded_chunks: int
    skipped_unchanged: int
    excluded_empty: int
    api_batches: int


class EmbeddingService:
    def __init__(
        self,
        *,
        client: OpenAIEmbeddingClient,
        store: EmbeddingStore,
        model: str,
        dimensions: int,
        batch_size: int,
    ):
        normalized_model = (model or "").strip()

        if not normalized_model:
            raise EmbeddingConfigurationError(
                "OPENAI_EMBEDDING_MODEL が設定されていません。"
            )

        if (
            not isinstance(dimensions, int)
            or isinstance(dimensions, bool)
            or dimensions < 1
        ):
            raise EmbeddingConfigurationError(
                "OPENAI_EMBEDDING_DIMENSIONSは1以上の整数が必要です。"
            )

        if (
            not isinstance(batch_size, int)
            or isinstance(batch_size, bool)
            or not 1 <= batch_size <= MAX_EMBEDDING_INPUTS
        ):
            raise EmbeddingConfigurationError(
                "OPENAI_EMBEDDING_BATCH_SIZEは1から2048の範囲が必要です。"
            )

        self._client = client
        self._store = store
        self._model = normalized_model
        self._dimensions = dimensions
        self._batch_size = batch_size

    def embed_chunks(
        self,
        chunks: Iterable[NotionChunk],
    ) -> EmbeddingRunResult:
        source_chunks = list(chunks)
        pending: list[tuple[NotionChunk, str, str]] = []
        excluded_empty = 0
        skipped_unchanged = 0
        seen_record_ids = set()

        for chunk in source_chunks:
            if not chunk.content.strip():
                excluded_empty += 1
                continue

            embedding_version = build_embedding_version(
                content_hash=chunk.content_hash,
                model=self._model,
                dimensions=self._dimensions,
            )
            record_id = build_embedding_record_id(
                chunk_id=chunk.chunk_id,
                embedding_version=embedding_version,
            )

            if record_id in seen_record_ids:
                skipped_unchanged += 1
                continue

            seen_record_ids.add(record_id)
            existing = self._store.get(
                chunk_id=chunk.chunk_id,
                embedding_version=embedding_version,
            )

            if _is_reusable_record(
                existing,
                chunk=chunk,
                model=self._model,
                dimensions=self._dimensions,
                record_id=record_id,
            ):
                skipped_unchanged += 1
                continue

            pending.append((chunk, embedding_version, record_id))

        embedded_chunks = 0
        api_batches = 0

        for offset in range(0, len(pending), self._batch_size):
            batch = pending[offset:offset + self._batch_size]
            vectors = self._client.create_embeddings(
                [chunk.content for chunk, _, _ in batch],
                model=self._model,
                dimensions=self._dimensions,
            )
            api_batches += 1
            embedded_at = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            records = [
                _build_record(
                    chunk=chunk,
                    embedding_version=embedding_version,
                    record_id=record_id,
                    model=self._model,
                    dimensions=self._dimensions,
                    embedding=embedding,
                    embedded_at=embedded_at,
                )
                for (chunk, embedding_version, record_id), embedding
                in zip(batch, vectors, strict=True)
            ]
            self._store.save_batch(records)
            embedded_chunks += len(records)

        return EmbeddingRunResult(
            total_chunks=len(source_chunks),
            embedded_chunks=embedded_chunks,
            skipped_unchanged=skipped_unchanged,
            excluded_empty=excluded_empty,
            api_batches=api_batches,
        )


def build_embedding_version(
    *,
    content_hash: str,
    model: str,
    dimensions: int,
) -> str:
    normalized_hash = (content_hash or "").strip().lower()
    normalized_model = (model or "").strip()

    if (
        not normalized_hash
        or not normalized_model
        or not isinstance(dimensions, int)
        or isinstance(dimensions, bool)
        or dimensions < 1
    ):
        raise EmbeddingConfigurationError(
            "Embedding versionの入力が不正です。"
        )

    source = f"{normalized_hash}\0{normalized_model}\0{dimensions}"
    return f"embedding:{hashlib.sha256(source.encode('utf-8')).hexdigest()}"


def build_embedding_record_id(
    *,
    chunk_id: str,
    embedding_version: str,
) -> str:
    normalized_chunk_id = (chunk_id or "").strip()
    normalized_version = (embedding_version or "").strip()

    if not normalized_chunk_id or not normalized_version:
        raise EmbeddingConfigurationError(
            "Embedding record IDの入力が不正です。"
        )

    source = f"{normalized_chunk_id}\0{normalized_version}"
    return f"embedding-record:{hashlib.sha256(source.encode('utf-8')).hexdigest()}"


def _is_reusable_record(
    record: dict | None,
    *,
    chunk: NotionChunk,
    model: str,
    dimensions: int,
    record_id: str,
) -> bool:
    if record is None:
        return False

    vector = record.get("embedding")
    return (
        record.get("record_id") == record_id
        and record.get("content_hash") == chunk.content_hash
        and record.get("model") == model
        and record.get("dimensions") == dimensions
        and isinstance(vector, list)
        and len(vector) == dimensions
    )


def _build_record(
    *,
    chunk: NotionChunk,
    embedding_version: str,
    record_id: str,
    model: str,
    dimensions: int,
    embedding: list[float],
    embedded_at: str,
) -> dict:
    metadata = chunk.to_dict()
    metadata.pop("content", None)
    return {
        "record_id": record_id,
        "chunk_id": chunk.chunk_id,
        "embedding_version": embedding_version,
        "content_hash": chunk.content_hash,
        "model": model,
        "dimensions": dimensions,
        "content": chunk.content,
        "embedding": embedding,
        "metadata": metadata,
        "embedded_at": embedded_at,
    }
