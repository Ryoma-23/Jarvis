import logging

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from app import config
from app.integrations.notion_client import NotionClient, NotionError
from app.integrations.notion_memory_store import (
    MEMORY_SYNC_KEY_PROPERTY,
    NotionMemoryStore,
)
from app.integrations.notion_resources import (
    resolve_memory_data_source_id,
)
from app.integrations.notion_store import canonical_notion_id
from app.repositories.common import (
    JsonListStore,
    MigrationResult,
    active_records,
    build_sync_key,
    ensure_iso_datetime,
    next_local_id,
    now_values,
)


logger = logging.getLogger(__name__)


class MemoryRepository:
    def __init__(
        self,
        *,
        local_path: Path,
        notion_store: NotionMemoryStore | None,
        read_from_notion: bool,
    ):
        self.local = JsonListStore(local_path)
        self.notion_store = notion_store
        self.read_from_notion = read_from_notion

    def load_all_local(self) -> list[dict[str, Any]]:
        return self.local.load()

    def save_all_local(self, memories: list[dict[str, Any]]) -> None:
        self.local.save(memories)

    def add(
        self,
        content: str,
        category: str = "other",
    ) -> dict[str, Any]:
        memories = self.local.load()
        memory_id = next_local_id(memories)
        created_at, created_at_iso = now_values()
        memory = {
            "id": memory_id,
            "content": content,
            "category": category or "other",
            "created_at": created_at,
            "created_at_iso": created_at_iso,
            "updated_at": created_at,
            "updated_at_iso": created_at_iso,
            "sync_key": build_sync_key(
                entity="memory",
                local_id=memory_id,
                content=content,
                created_at=created_at,
            ),
            "notion_page_id": None,
            "notion_sync_status": "pending",
        }
        memories.append(memory)
        self.local.save(memories)
        self._sync_memory(memory, memories)
        return memory

    def list(self) -> list[dict[str, Any]]:
        if self.read_from_notion and self.notion_store is not None:
            try:
                memories = self.notion_store.list_memories()
                return self._exclude_local_tombstones(memories)
            except NotionError as error:
                _log_notion_fallback("list", error)
            except Exception as error:
                _log_unexpected_fallback("list", error)

        return active_records(self.local.load())

    def search(self, keyword: str) -> list[dict[str, Any]]:
        if self.read_from_notion and self.notion_store is not None:
            try:
                memories = self.notion_store.search_memories(keyword)
                return self._exclude_local_tombstones(memories)
            except NotionError as error:
                _log_notion_fallback("search", error)
            except Exception as error:
                _log_unexpected_fallback("search", error)

        lowered = keyword.lower()
        return [
            memory
            for memory in active_records(self.local.load())
            if lowered in memory["content"].lower()
            or lowered in memory["category"].lower()
        ]

    def update(
        self,
        memory_ids: list[int],
        content: str,
        category: str | None = None,
    ) -> list[int]:
        memories = self.local.load()
        targets = [
            memory
            for memory in active_records(memories)
            if memory.get("id") in memory_ids
        ]

        if not targets:
            return []

        updated_at, updated_at_iso = now_values()

        for memory in targets:
            self._normalize_memory(memory)
            memory["content"] = content

            if category:
                memory["category"] = category

            memory["updated_at"] = updated_at
            memory["updated_at_iso"] = updated_at_iso
            memory["notion_sync_status"] = "pending"

        self.local.save(memories)

        for memory in targets:
            self._sync_memory(memory, memories)

        return [memory["id"] for memory in targets]

    def delete(self, memory_ids: list[int]) -> list[int]:
        memories = self.local.load()
        targets = [
            memory
            for memory in active_records(memories)
            if memory.get("id") in memory_ids
        ]

        if not targets:
            return []

        deleted_at, deleted_at_iso = now_values()

        for memory in targets:
            memory["deleted_at"] = deleted_at
            memory["deleted_at_iso"] = deleted_at_iso
            memory["notion_sync_status"] = (
                "delete_pending"
                if memory.get("notion_page_id")
                else "deleted"
            )

        self.local.save(memories)

        for memory in targets:
            self._trash_memory(memory, memories)

        return [memory["id"] for memory in targets]

    def migrate(self, *, dry_run: bool) -> MigrationResult:
        if self.notion_store is None:
            raise ValueError("Memory用Notion Repositoryが設定されていません。")

        self.notion_store.validate_schema()
        memories = self.local.load()
        active = active_records(memories)
        already_synced = 0
        existing_in_notion = 0
        would_create = 0
        migrated = 0
        delete_pending = 0
        deleted_in_notion = 0

        for stored_memory in active:
            memory = deepcopy(stored_memory)
            self._normalize_memory(memory)
            existing_pages = self.notion_store.find_by_rich_text(
                MEMORY_SYNC_KEY_PROPERTY,
                memory["sync_key"],
            )

            if len(existing_pages) > 1:
                raise ValueError(
                    "MemoryのSync KeyがNotion上で重複しています。"
                )

            if existing_pages:
                existing_in_notion += 1
            else:
                would_create += 1

            if (
                stored_memory.get("notion_sync_status") == "synced"
                and stored_memory.get("notion_page_id")
            ):
                already_synced += 1

            if dry_run:
                continue

            result = self.notion_store.sync_memory(memory)
            stored_memory.update(memory)
            stored_memory["notion_page_id"] = result.page_id
            stored_memory["notion_sync_status"] = "synced"
            migrated += 1

        for memory in memories:
            if memory.get("notion_sync_status") != "delete_pending":
                continue

            delete_pending += 1

            if dry_run:
                continue

            self.notion_store.trash_page(memory["notion_page_id"])
            memory["notion_sync_status"] = "deleted"
            deleted_in_notion += 1

        if not dry_run:
            self.local.save(memories)

        return MigrationResult(
            entity="memory",
            dry_run=dry_run,
            active_records=len(active),
            already_synced=already_synced,
            existing_in_notion=existing_in_notion,
            would_create=would_create,
            migrated=migrated,
            delete_pending=delete_pending,
            deleted_in_notion=deleted_in_notion,
        )

    def _normalize_memory(self, memory: dict[str, Any]) -> None:
        ensure_iso_datetime(
            memory,
            local_key="created_at",
            iso_key="created_at_iso",
        )
        ensure_iso_datetime(
            memory,
            local_key="updated_at",
            iso_key="updated_at_iso",
        )

        if not memory.get("sync_key"):
            memory["sync_key"] = build_sync_key(
                entity="memory",
                local_id=memory["id"],
                content=memory["content"],
                created_at=memory["created_at"],
            )

        memory.setdefault("notion_page_id", None)
        memory.setdefault("notion_sync_status", "pending")

    def _sync_memory(
        self,
        memory: dict[str, Any],
        memories: list[dict[str, Any]],
    ) -> None:
        if self.notion_store is None:
            return

        try:
            result = self.notion_store.sync_memory(memory)
        except NotionError as error:
            logger.warning(
                "Notion memory sync remains pending: memory_id=%s error=%s",
                memory["id"],
                error,
            )
            return
        except Exception as error:
            logger.warning(
                "Unexpected Notion memory sync failure: "
                "memory_id=%s error_type=%s",
                memory["id"],
                type(error).__name__,
            )
            return

        memory["notion_page_id"] = result.page_id
        memory["notion_sync_status"] = "synced"
        self.local.save(memories)

    def _trash_memory(
        self,
        memory: dict[str, Any],
        memories: list[dict[str, Any]],
    ) -> None:
        if self.notion_store is None or not memory.get("notion_page_id"):
            return

        try:
            self.notion_store.trash_page(memory["notion_page_id"])
        except NotionError as error:
            logger.warning(
                "Notion memory trash remains pending: "
                "memory_id=%s error=%s",
                memory["id"],
                error,
            )
            return
        except Exception as error:
            logger.warning(
                "Unexpected Notion memory trash failure: "
                "memory_id=%s error_type=%s",
                memory["id"],
                type(error).__name__,
            )
            return

        memory["notion_sync_status"] = "deleted"
        self.local.save(memories)

    def _exclude_local_tombstones(
        self,
        notion_memories: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        deleted_page_ids = {
            canonical_notion_id(memory["notion_page_id"])
            for memory in self.local.load()
            if memory.get("deleted_at") and memory.get("notion_page_id")
        }
        return [
            memory
            for memory in notion_memories
            if not isinstance(memory.get("notion_page_id"), str)
            or canonical_notion_id(memory["notion_page_id"])
            not in deleted_page_ids
        ]


def build_memory_repository(
    *,
    local_path: Path | None = None,
) -> MemoryRepository:
    data_source_id = resolve_memory_data_source_id()
    notion_store = None

    if config.NOTION_API_TOKEN and data_source_id:
        notion_store = _build_notion_store(
            config.NOTION_API_TOKEN,
            config.NOTION_API_VERSION,
            data_source_id,
        )

    return MemoryRepository(
        local_path=local_path or config.MEMORY_FILE,
        notion_store=notion_store,
        read_from_notion=config.NOTION_MEMORY_READ_ENABLED,
    )


@lru_cache(maxsize=8)
def _build_notion_store(
    api_token: str,
    api_version: str,
    data_source_id: str,
) -> NotionMemoryStore:
    return NotionMemoryStore(
        client=NotionClient(
            api_token=api_token,
            api_version=api_version,
        ),
        data_source_id=data_source_id,
    )


def _log_notion_fallback(operation: str, error: Exception) -> None:
    logger.warning(
        "Notion memory read failed; using Local fallback: "
        "operation=%s error=%s",
        operation,
        error,
    )


def _log_unexpected_fallback(
    operation: str,
    error: Exception,
) -> None:
    logger.warning(
        "Unexpected Notion memory read failure; using Local fallback: "
        "operation=%s error_type=%s",
        operation,
        type(error).__name__,
    )
