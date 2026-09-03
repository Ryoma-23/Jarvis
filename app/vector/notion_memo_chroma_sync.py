from dataclasses import dataclass

from app.chunking.notion_memo_chunker import NotionMemoChunker
from app.embeddings.embedding_store import EmbeddingStoreError
from app.integrations.notion_client import NotionError
from app.integrations.notion_memo_reader import NotionMemoReader
from app.integrations.openai_embedding_client import EmbeddingError
from app.vector.chroma_index import ChromaIndexError
from app.vector.notion_chroma_sync import NotionChromaSyncService


@dataclass(frozen=True)
class NotionMemoChromaSyncFailure:
    notion_page_id: str
    local_id: int | None
    error_type: str
    message: str


@dataclass(frozen=True)
class NotionMemoChromaSyncSummary:
    dry_run: bool
    total_pages: int
    pages_with_content: int
    empty_pages: int
    candidate_chunks: int
    synced_pages: int
    embedded_chunks: int
    skipped_unchanged: int
    deleted_chunks: int
    failures: tuple[NotionMemoChromaSyncFailure, ...]


class NotionMemoChromaSyncService:
    def __init__(
        self,
        *,
        reader: NotionMemoReader,
        chunker: NotionMemoChunker,
        chroma_sync_service: NotionChromaSyncService | None = None,
    ):
        self._reader = reader
        self._chunker = chunker
        self._chroma_sync_service = chroma_sync_service

    def sync_all(
        self,
        *,
        dry_run: bool = True,
    ) -> NotionMemoChromaSyncSummary:
        if not dry_run and self._chroma_sync_service is None:
            raise ChromaIndexError(
                "Apply実行にNotion Chroma同期Serviceが設定されていません。"
            )

        memos = self._reader.list_notes_for_indexing()
        pages_with_content = 0
        empty_pages = 0
        candidate_chunks = 0
        synced_pages = 0
        embedded_chunks = 0
        skipped_unchanged = 0
        deleted_chunks = 0
        failures = []

        for memo in memos:
            page_id = _optional_text(memo.get("notion_page_id"))
            local_id = _optional_integer(memo.get("id"))

            try:
                chunks = self._chunker.chunk(memo)
                candidate_chunks += len(chunks)

                if chunks:
                    pages_with_content += 1
                else:
                    empty_pages += 1

                if dry_run:
                    continue

                if self._chroma_sync_service is None:
                    raise ChromaIndexError(
                        "Apply実行にNotion Chroma同期Serviceがありません。"
                    )

                result = self._chroma_sync_service.sync_chunks(
                    notion_page_id=page_id,
                    chunks=chunks,
                )
                synced_pages += 1
                embedded_chunks += result.embedding_result.embedded_chunks
                skipped_unchanged += (
                    result.embedding_result.skipped_unchanged
                )
                deleted_chunks += result.chroma_result.deleted_chunks
            except (
                NotionError,
                EmbeddingError,
                EmbeddingStoreError,
                ChromaIndexError,
            ) as error:
                failures.append(
                    NotionMemoChromaSyncFailure(
                        notion_page_id=page_id,
                        local_id=local_id,
                        error_type=type(error).__name__,
                        message=str(error),
                    )
                )

        return NotionMemoChromaSyncSummary(
            dry_run=dry_run,
            total_pages=len(memos),
            pages_with_content=pages_with_content,
            empty_pages=empty_pages,
            candidate_chunks=candidate_chunks,
            synced_pages=synced_pages,
            embedded_chunks=embedded_chunks,
            skipped_unchanged=skipped_unchanged,
            deleted_chunks=deleted_chunks,
            failures=tuple(failures),
        )


def _optional_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_integer(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value

    return None
