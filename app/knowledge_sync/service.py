import time

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar

from app.chunking.notion_chunker import NotionPageChunkingService
from app.chunking.notion_memo_chunker import (
    NOTION_MEMO_SOURCE_TYPE,
    NotionMemoChunker,
)
from app.integrations.notion_client import (
    NotionConnectionError,
    NotionRateLimitError,
    NotionResourceNotFoundError,
    NotionResponseError,
    NotionServerError,
)
from app.integrations.notion_memo_reader import NotionMemoReader
from app.integrations.openai_embedding_client import EmbeddingAPIError
from app.knowledge_sync.registry import (
    KnowledgePageSource,
    KnowledgeSourceRegistry,
    canonical_notion_id,
)
from app.knowledge_sync.state import (
    KnowledgeSyncState,
    KnowledgeSyncStateStore,
)
from app.vector.chroma_index import (
    ChromaIndex,
    ChromaIndexError,
    IndexedNotionPage,
)
from app.vector.notion_chroma_sync import NotionChromaSyncService


NOTION_PAGE_SOURCE_TYPE = "notion_page"
_T = TypeVar("_T")


@dataclass(frozen=True)
class KnowledgeSyncAction:
    notion_page_id: str
    source_type: str
    status: str
    reason: str
    chunk_count: int = 0
    embedded_chunks: int = 0
    skipped_embeddings: int = 0
    deleted_chunks: int = 0


@dataclass(frozen=True)
class KnowledgeSyncSummary:
    dry_run: bool
    collection_name: str
    actions: tuple[KnowledgeSyncAction, ...]

    @property
    def failures(self) -> tuple[KnowledgeSyncAction, ...]:
        return tuple(action for action in self.actions if action.status == "failed")

    @property
    def changed_pages(self) -> int:
        return sum(
            action.status in {"synced", "would_sync"}
            for action in self.actions
        )

    @property
    def unchanged_pages(self) -> int:
        return sum(action.status == "skipped" for action in self.actions)

    @property
    def removed_pages(self) -> int:
        return sum(
            action.status in {"deleted", "would_delete"}
            for action in self.actions
        )


class NotionKnowledgeSyncService:
    def __init__(
        self,
        *,
        registry: KnowledgeSourceRegistry,
        page_chunking_service: NotionPageChunkingService,
        memo_chunker: NotionMemoChunker,
        memo_reader: NotionMemoReader | None,
        chroma_index: ChromaIndex,
        state_store: KnowledgeSyncStateStore,
        embedding_model: str,
        embedding_dimensions: int,
        chroma_sync_service: NotionChromaSyncService | None = None,
        retry_count: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if retry_count < 1:
            raise ValueError("retry_countは1以上が必要です。")

        self._registry = registry
        self._page_chunking_service = page_chunking_service
        self._memo_chunker = memo_chunker
        self._memo_reader = memo_reader
        self._chroma_index = chroma_index
        self._state_store = state_store
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._chroma_sync_service = chroma_sync_service
        self._retry_count = retry_count
        self._sleeper = sleeper

    def run(self, *, dry_run: bool = True) -> KnowledgeSyncSummary:
        if not dry_run and self._chroma_sync_service is None:
            raise ChromaIndexError(
                "Apply実行にNotion Chroma同期Serviceが設定されていません。"
            )

        indexed_pages = {
            page.notion_page_key: page
            for page in self._chroma_index.list_indexed_pages()
        }
        state = self._state_store.load(
            collection_name=self._chroma_index.collection_name,
            embedding_model=self._embedding_model,
            embedding_dimensions=self._embedding_dimensions,
        )
        actions: list[KnowledgeSyncAction] = []
        deleted_keys: set[str] = set()

        for source in self._registry.pages:
            try:
                action = self._sync_registered_page(
                    source=source,
                    indexed_page=indexed_pages.get(source.page_key),
                    state=state,
                    dry_run=dry_run,
                )
            except Exception as error:
                action = _failure_action(
                    page_id=source.page_id,
                    source_type=NOTION_PAGE_SOURCE_TYPE,
                    error=error,
                )

            actions.append(action)

            if action.status in {"deleted", "would_delete"}:
                deleted_keys.add(source.page_key)

        memo_query_succeeded = False
        current_memo_keys: set[str] = set()

        if self._registry.include_notes:
            if self._memo_reader is None:
                actions.append(
                    KnowledgeSyncAction(
                        notion_page_id="notes_data_source",
                        source_type=NOTION_MEMO_SOURCE_TYPE,
                        status="failed",
                        reason="Notes用Data Source IDが設定されていません。",
                    )
                )
            else:
                try:
                    memos = self._with_retry(self._memo_reader.list_notes)
                    memo_query_succeeded = True
                except Exception as error:
                    actions.append(
                        _failure_action(
                            page_id="notes_data_source",
                            source_type=NOTION_MEMO_SOURCE_TYPE,
                            error=error,
                        )
                    )
                    memos = []

                for memo in memos:
                    page_id = _required_mapping_text(
                        memo,
                        "notion_page_id",
                    )
                    page_key = canonical_notion_id(page_id)
                    current_memo_keys.add(page_key)
                    try:
                        action = self._sync_memo(
                            memo=memo,
                            indexed_page=indexed_pages.get(page_key),
                            state=state,
                            dry_run=dry_run,
                        )
                    except Exception as error:
                        action = _failure_action(
                            page_id=page_id,
                            source_type=NOTION_MEMO_SOURCE_TYPE,
                            error=error,
                        )

                    actions.append(action)

        configured_page_keys = {
            source.page_key for source in self._registry.pages
        }

        for page_key, indexed_page in indexed_pages.items():
            if page_key in deleted_keys:
                continue

            source_types = set(indexed_page.source_types)
            should_remove = False
            reason = ""

            if (
                self._registry.authoritative
                and NOTION_PAGE_SOURCE_TYPE in source_types
                and page_key not in configured_page_keys
            ):
                should_remove = True
                reason = "unregistered_source"
            elif (
                NOTION_MEMO_SOURCE_TYPE in source_types
                and (
                    (memo_query_succeeded and page_key not in current_memo_keys)
                    or (
                        self._registry.authoritative
                        and not self._registry.include_notes
                    )
                )
            ):
                should_remove = True
                reason = "source_removed"

            if not should_remove:
                continue

            actions.append(
                self._delete_indexed_page(
                    indexed_page=indexed_page,
                    source_type=(
                        NOTION_MEMO_SOURCE_TYPE
                        if NOTION_MEMO_SOURCE_TYPE in source_types
                        else NOTION_PAGE_SOURCE_TYPE
                    ),
                    reason=reason,
                    state=state,
                    dry_run=dry_run,
                )
            )

        if not dry_run:
            self._state_store.save(state)

        return KnowledgeSyncSummary(
            dry_run=dry_run,
            collection_name=self._chroma_index.collection_name,
            actions=tuple(actions),
        )

    def _sync_registered_page(
        self,
        *,
        source: KnowledgePageSource,
        indexed_page: IndexedNotionPage | None,
        state: KnowledgeSyncState,
        dry_run: bool,
    ) -> KnowledgeSyncAction:
        try:
            page = self._with_retry(
                lambda: self._page_chunking_service.retrieve_page(
                    source.page_id
                )
            )
        except NotionResourceNotFoundError:
            return self._delete_page_by_id(
                page_id=source.page_id,
                source_type=NOTION_PAGE_SOURCE_TYPE,
                reason="not_found",
                indexed_page=indexed_page,
                state=state,
                dry_run=dry_run,
            )

        page_id = _required_mapping_text(page, "id")
        page_key = canonical_notion_id(page_id)

        if page_key != source.page_key:
            raise NotionResponseError(
                "登録Page IDとNotionから取得したPage IDが一致しません。"
            )

        if page.get("in_trash") is True or page.get("archived") is True:
            return self._delete_page_by_id(
                page_id=page_id,
                source_type=NOTION_PAGE_SOURCE_TYPE,
                reason="in_trash",
                indexed_page=indexed_page,
                state=state,
                dry_run=dry_run,
            )

        last_edited_time = _required_mapping_text(page, "last_edited_time")

        if _is_current(
            state=state,
            page_id=page_id,
            source_type=NOTION_PAGE_SOURCE_TYPE,
            last_edited_time=last_edited_time,
            indexed_page=indexed_page,
        ):
            chunk_count = len(indexed_page.chunk_ids) if indexed_page else 0
            if not dry_run:
                _record_state(
                    state=state,
                    page_id=page_id,
                    source_type=NOTION_PAGE_SOURCE_TYPE,
                    last_edited_time=last_edited_time,
                    chunk_count=chunk_count,
                )
            return KnowledgeSyncAction(
                notion_page_id=page_id,
                source_type=NOTION_PAGE_SOURCE_TYPE,
                status="skipped",
                reason="unchanged",
                chunk_count=chunk_count,
            )

        chunks = self._with_retry(
            lambda: self._page_chunking_service.chunk_retrieved_page(page)
        )
        return self._apply_chunks(
            page_id=page_id,
            source_type=NOTION_PAGE_SOURCE_TYPE,
            last_edited_time=last_edited_time,
            chunks=chunks,
            state=state,
            dry_run=dry_run,
        )

    def _sync_memo(
        self,
        *,
        memo: dict[str, Any],
        indexed_page: IndexedNotionPage | None,
        state: KnowledgeSyncState,
        dry_run: bool,
    ) -> KnowledgeSyncAction:
        page_id = _required_mapping_text(memo, "notion_page_id")
        last_edited_time = _required_mapping_text(
            memo,
            "notion_last_edited_time",
        )

        if _is_current(
            state=state,
            page_id=page_id,
            source_type=NOTION_MEMO_SOURCE_TYPE,
            last_edited_time=last_edited_time,
            indexed_page=indexed_page,
        ):
            chunk_count = len(indexed_page.chunk_ids) if indexed_page else 0
            if not dry_run:
                _record_state(
                    state=state,
                    page_id=page_id,
                    source_type=NOTION_MEMO_SOURCE_TYPE,
                    last_edited_time=last_edited_time,
                    chunk_count=chunk_count,
                )
            return KnowledgeSyncAction(
                notion_page_id=page_id,
                source_type=NOTION_MEMO_SOURCE_TYPE,
                status="skipped",
                reason="unchanged",
                chunk_count=chunk_count,
            )

        if self._memo_reader is None:
            raise NotionResponseError("Notion Memo Readerがありません。")

        hydrated = self._with_retry(
            lambda: self._memo_reader.hydrate_content_for_indexing(memo)
        )
        chunks = self._memo_chunker.chunk(hydrated)
        return self._apply_chunks(
            page_id=page_id,
            source_type=NOTION_MEMO_SOURCE_TYPE,
            last_edited_time=last_edited_time,
            chunks=chunks,
            state=state,
            dry_run=dry_run,
        )

    def _apply_chunks(
        self,
        *,
        page_id: str,
        source_type: str,
        last_edited_time: str,
        chunks: list[Any],
        state: KnowledgeSyncState,
        dry_run: bool,
    ) -> KnowledgeSyncAction:
        if dry_run:
            return KnowledgeSyncAction(
                notion_page_id=page_id,
                source_type=source_type,
                status="would_sync",
                reason="new_or_changed",
                chunk_count=len(chunks),
            )

        if self._chroma_sync_service is None:
            raise ChromaIndexError("Notion Chroma同期Serviceがありません。")

        result = self._with_retry(
            lambda: self._chroma_sync_service.sync_chunks(
                notion_page_id=page_id,
                chunks=chunks,
            )
        )
        _record_state(
            state=state,
            page_id=page_id,
            source_type=source_type,
            last_edited_time=last_edited_time,
            chunk_count=result.chunk_count,
        )
        return KnowledgeSyncAction(
            notion_page_id=page_id,
            source_type=source_type,
            status="synced",
            reason="new_or_changed",
            chunk_count=result.chunk_count,
            embedded_chunks=result.embedding_result.embedded_chunks,
            skipped_embeddings=result.embedding_result.skipped_unchanged,
            deleted_chunks=result.chroma_result.deleted_chunks,
        )

    def _delete_page_by_id(
        self,
        *,
        page_id: str,
        source_type: str,
        reason: str,
        indexed_page: IndexedNotionPage | None,
        state: KnowledgeSyncState,
        dry_run: bool,
    ) -> KnowledgeSyncAction:
        if indexed_page is None:
            if not dry_run:
                state.remove(page_id)
            return KnowledgeSyncAction(
                notion_page_id=page_id,
                source_type=source_type,
                status="skipped",
                reason=reason,
            )

        return self._delete_indexed_page(
            indexed_page=indexed_page,
            source_type=source_type,
            reason=reason,
            state=state,
            dry_run=dry_run,
        )

    def _delete_indexed_page(
        self,
        *,
        indexed_page: IndexedNotionPage,
        source_type: str,
        reason: str,
        state: KnowledgeSyncState,
        dry_run: bool,
    ) -> KnowledgeSyncAction:
        deleted_chunks = len(indexed_page.chunk_ids)

        if not dry_run:
            deleted_chunks = self._with_retry(
                lambda: self._chroma_index.delete_page(
                    indexed_page.notion_page_id
                )
            )
            state.remove(indexed_page.notion_page_id)

        return KnowledgeSyncAction(
            notion_page_id=indexed_page.notion_page_id,
            source_type=source_type,
            status="would_delete" if dry_run else "deleted",
            reason=reason,
            deleted_chunks=deleted_chunks,
        )

    def _with_retry(self, operation: Callable[[], _T]) -> _T:
        for attempt in range(1, self._retry_count + 1):
            try:
                return operation()
            except (
                NotionConnectionError,
                NotionRateLimitError,
                NotionServerError,
                EmbeddingAPIError,
                ChromaIndexError,
            ) as error:
                if attempt >= self._retry_count:
                    raise

                delay = _retry_delay(error, attempt)
                self._sleeper(delay)

        raise RuntimeError("Notion知識同期の再試行に失敗しました。")


def _is_current(
    *,
    state: KnowledgeSyncState,
    page_id: str,
    source_type: str,
    last_edited_time: str,
    indexed_page: IndexedNotionPage | None,
) -> bool:
    page_key = canonical_notion_id(page_id)
    record = state.pages.get(page_key)

    if isinstance(record, dict) and (
        record.get("source_type") == source_type
        and record.get("last_edited_time") == last_edited_time
    ):
        chunk_count = record.get("chunk_count")

        if chunk_count == 0:
            return indexed_page is None or not indexed_page.chunk_ids

        return (
            indexed_page is not None
            and len(indexed_page.chunk_ids) == chunk_count
            and indexed_page.source_types == (source_type,)
            and indexed_page.last_edited_times == (last_edited_time,)
        )

    return (
        indexed_page is not None
        and indexed_page.source_types == (source_type,)
        and indexed_page.last_edited_times == (last_edited_time,)
    )


def _record_state(
    *,
    state: KnowledgeSyncState,
    page_id: str,
    source_type: str,
    last_edited_time: str,
    chunk_count: int,
) -> None:
    state.record(
        page_id=page_id,
        source_type=source_type,
        last_edited_time=last_edited_time,
        chunk_count=chunk_count,
        synced_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def _retry_delay(error: Exception, attempt: int) -> float:
    if isinstance(error, NotionRateLimitError):
        try:
            retry_after = float(error.retry_after or "")
        except ValueError:
            retry_after = 0.0

        if retry_after > 0:
            return min(retry_after, 60.0)

    return min(float(2 ** (attempt - 1)), 30.0)


def _failure_action(
    *,
    page_id: str,
    source_type: str,
    error: Exception,
) -> KnowledgeSyncAction:
    return KnowledgeSyncAction(
        notion_page_id=page_id,
        source_type=source_type,
        status="failed",
        reason=f"{type(error).__name__}: {error}",
    )


def _required_mapping_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)

    if not isinstance(value, str) or not value.strip():
        raise NotionResponseError(
            f"Notion同期対象の{key}を取得できませんでした。"
        )

    return value.strip()
