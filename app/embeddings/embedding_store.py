import json
import sqlite3

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.config import EMBEDDINGS_DB_FILE


EMBEDDING_STORE_SCHEMA_VERSION = 1


class EmbeddingStoreError(RuntimeError):
    """Raised when local Embedding state cannot be read or saved."""


class EmbeddingStore:
    """SQLite persistence for generated vectors; not a vector search DB."""

    def __init__(
        self,
        db_path: str | Path = EMBEDDINGS_DB_FILE,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()

        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()

        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_schema(self) -> None:
        try:
            with self._connection() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    f"""
                    CREATE TABLE IF NOT EXISTS embeddings (
                        record_id TEXT PRIMARY KEY,
                        chunk_id TEXT NOT NULL,
                        embedding_version TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        model TEXT NOT NULL,
                        dimensions INTEGER NOT NULL CHECK (dimensions > 0),
                        content TEXT NOT NULL,
                        vector_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        embedded_at TEXT NOT NULL,
                        UNIQUE (chunk_id, embedding_version)
                    );

                    CREATE INDEX IF NOT EXISTS idx_embeddings_chunk_id
                    ON embeddings(chunk_id);

                    PRAGMA user_version = {EMBEDDING_STORE_SCHEMA_VERSION};
                    """
                )
                connection.commit()
        except sqlite3.Error:
            raise EmbeddingStoreError(
                "Embedding Storeを初期化できませんでした。"
            ) from None

    def get(
        self,
        *,
        chunk_id: str,
        embedding_version: str,
    ) -> dict[str, Any] | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM embeddings
                    WHERE chunk_id = ? AND embedding_version = ?
                    """,
                    (chunk_id, embedding_version),
                ).fetchone()
        except sqlite3.Error:
            raise EmbeddingStoreError(
                "Embedding Storeを読み込めませんでした。"
            ) from None

        return _row_to_record(row) if row is not None else None

    def save_batch(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return

        values = [_record_values(record) for record in records]

        try:
            with self._transaction() as connection:
                connection.executemany(
                    """
                    INSERT INTO embeddings (
                        record_id,
                        chunk_id,
                        embedding_version,
                        content_hash,
                        model,
                        dimensions,
                        content,
                        vector_json,
                        metadata_json,
                        embedded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_id) DO UPDATE SET
                        content_hash = excluded.content_hash,
                        model = excluded.model,
                        dimensions = excluded.dimensions,
                        content = excluded.content,
                        vector_json = excluded.vector_json,
                        metadata_json = excluded.metadata_json,
                        embedded_at = excluded.embedded_at
                    """,
                    values,
                )
        except (sqlite3.Error, TypeError, ValueError):
            raise EmbeddingStoreError(
                "Embedding Storeへ保存できませんでした。"
            ) from None

    def list_records(self) -> list[dict[str, Any]]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM embeddings
                    ORDER BY embedded_at, record_id
                    """
                ).fetchall()
        except sqlite3.Error:
            raise EmbeddingStoreError(
                "Embedding Storeを読み込めませんでした。"
            ) from None

        return [_row_to_record(row) for row in rows]

    def count(self) -> int:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM embeddings"
                ).fetchone()
        except sqlite3.Error:
            raise EmbeddingStoreError(
                "Embedding Storeを読み込めませんでした。"
            ) from None

        return int(row["count"])


def _record_values(record: dict[str, Any]) -> tuple[Any, ...]:
    required_text = (
        "record_id",
        "chunk_id",
        "embedding_version",
        "content_hash",
        "model",
        "content",
        "embedded_at",
    )

    for key in required_text:
        value = record.get(key)

        if not isinstance(value, str) or not value.strip():
            raise EmbeddingStoreError(
                f"Embedding recordの{key}が不正です。"
            )

    dimensions = record.get("dimensions")
    vector = record.get("embedding")
    metadata = record.get("metadata")

    if (
        not isinstance(dimensions, int)
        or isinstance(dimensions, bool)
        or dimensions < 1
    ):
        raise EmbeddingStoreError(
            "Embedding recordのdimensionsが不正です。"
        )

    if not isinstance(vector, list) or len(vector) != dimensions:
        raise EmbeddingStoreError(
            "Embedding recordのvector次元数が一致しません。"
        )

    if not isinstance(metadata, dict):
        raise EmbeddingStoreError(
            "Embedding recordのmetadataが不正です。"
        )

    return (
        record["record_id"],
        record["chunk_id"],
        record["embedding_version"],
        record["content_hash"],
        record["model"],
        dimensions,
        record["content"],
        json.dumps(vector, ensure_ascii=False, separators=(",", ":")),
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
        record["embedded_at"],
    )


def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    try:
        vector = json.loads(row["vector_json"])
        metadata = json.loads(row["metadata_json"])
    except (json.JSONDecodeError, TypeError):
        raise EmbeddingStoreError(
            "Embedding Storeに不正なJSONがあります。"
        ) from None

    return {
        "record_id": row["record_id"],
        "chunk_id": row["chunk_id"],
        "embedding_version": row["embedding_version"],
        "content_hash": row["content_hash"],
        "model": row["model"],
        "dimensions": row["dimensions"],
        "content": row["content"],
        "embedding": vector,
        "metadata": metadata,
        "embedded_at": row["embedded_at"],
    }
