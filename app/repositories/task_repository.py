import logging

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from app import config
from app.integrations.notion_client import NotionClient, NotionError
from app.integrations.notion_resources import (
    resolve_tasks_data_source_id,
)
from app.integrations.notion_store import canonical_notion_id
from app.integrations.notion_task_store import (
    TASK_SYNC_KEY_PROPERTY,
    NotionTaskStore,
)
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


class TaskRepository:
    def __init__(
        self,
        *,
        local_path: Path,
        notion_store: NotionTaskStore | None,
        read_from_notion: bool,
    ):
        self.local = JsonListStore(local_path)
        self.notion_store = notion_store
        self.read_from_notion = read_from_notion

    def load_all_local(self) -> list[dict[str, Any]]:
        return self.local.load()

    def save_all_local(self, tasks: list[dict[str, Any]]) -> None:
        self.local.save(tasks)

    def add(
        self,
        title: str,
        due_date: str | None = None,
    ) -> dict[str, Any]:
        tasks = self.local.load()
        task_id = next_local_id(tasks)
        created_at, created_at_iso = now_values()
        task = {
            "id": task_id,
            "title": title,
            "status": "todo",
            "due_date": due_date,
            "created_at": created_at,
            "created_at_iso": created_at_iso,
            "completed_at": None,
            "completed_at_iso": None,
            "sync_key": build_sync_key(
                entity="task",
                local_id=task_id,
                content=title,
                created_at=created_at,
            ),
            "notion_page_id": None,
            "notion_sync_status": "pending",
        }
        tasks.append(task)
        self.local.save(tasks)
        self._sync_task(task, tasks)
        return task

    def list(self, status_filter: str = "all") -> list[dict[str, Any]]:
        if self.read_from_notion and self.notion_store is not None:
            try:
                tasks = self.notion_store.list_tasks(status_filter)
                return self._exclude_local_tombstones(tasks)
            except NotionError as error:
                _log_notion_fallback("list", error)
            except Exception as error:
                _log_unexpected_fallback("list", error)

        tasks = active_records(self.local.load())

        if status_filter in {"todo", "done"}:
            return [
                task
                for task in tasks
                if task.get("status") == status_filter
            ]

        return tasks

    def search(self, keyword: str) -> list[dict[str, Any]]:
        if self.read_from_notion and self.notion_store is not None:
            try:
                tasks = self.notion_store.search_title(keyword)
                return self._exclude_local_tombstones(tasks)
            except NotionError as error:
                _log_notion_fallback("search", error)
            except Exception as error:
                _log_unexpected_fallback("search", error)

        lowered = keyword.lower()
        return [
            task
            for task in active_records(self.local.load())
            if lowered in task["title"].lower()
        ]

    def complete(self, task_ids: list[int]) -> list[int]:
        tasks = self.local.load()
        targets = [
            task
            for task in active_records(tasks)
            if task.get("id") in task_ids
        ]

        if not targets:
            return []

        completed_at, completed_at_iso = now_values()

        for task in targets:
            self._normalize_task(task)
            task["status"] = "done"
            task["completed_at"] = completed_at
            task["completed_at_iso"] = completed_at_iso
            task["notion_sync_status"] = "pending"

        self.local.save(tasks)

        for task in targets:
            self._sync_task(task, tasks)

        return [task["id"] for task in targets]

    def delete(self, task_ids: list[int]) -> list[int]:
        tasks = self.local.load()
        targets = [
            task
            for task in active_records(tasks)
            if task.get("id") in task_ids
        ]

        if not targets:
            return []

        deleted_at, deleted_at_iso = now_values()

        for task in targets:
            task["deleted_at"] = deleted_at
            task["deleted_at_iso"] = deleted_at_iso
            task["notion_sync_status"] = (
                "delete_pending"
                if task.get("notion_page_id")
                else "deleted"
            )

        self.local.save(tasks)

        for task in targets:
            self._trash_task(task, tasks)

        return [task["id"] for task in targets]

    def migrate(self, *, dry_run: bool) -> MigrationResult:
        if self.notion_store is None:
            raise ValueError("Tasks用Notion Repositoryが設定されていません。")

        self.notion_store.validate_schema()
        tasks = self.local.load()
        active = active_records(tasks)
        already_synced = 0
        existing_in_notion = 0
        would_create = 0
        migrated = 0
        delete_pending = 0
        deleted_in_notion = 0

        for stored_task in active:
            task = deepcopy(stored_task)
            self._normalize_task(task)
            existing_pages = self.notion_store.find_by_rich_text(
                TASK_SYNC_KEY_PROPERTY,
                task["sync_key"],
            )

            if len(existing_pages) > 1:
                raise ValueError(
                    "TaskのSync KeyがNotion上で重複しています。"
                )

            if existing_pages:
                existing_in_notion += 1
            else:
                would_create += 1

            if (
                stored_task.get("notion_sync_status") == "synced"
                and stored_task.get("notion_page_id")
            ):
                already_synced += 1

            if dry_run:
                continue

            result = self.notion_store.sync_task(task)
            stored_task.update(task)
            stored_task["notion_page_id"] = result.page_id
            stored_task["notion_sync_status"] = "synced"
            migrated += 1

        for task in tasks:
            if task.get("notion_sync_status") != "delete_pending":
                continue

            delete_pending += 1

            if dry_run:
                continue

            self.notion_store.trash_page(task["notion_page_id"])
            task["notion_sync_status"] = "deleted"
            deleted_in_notion += 1

        if not dry_run:
            self.local.save(tasks)

        return MigrationResult(
            entity="tasks",
            dry_run=dry_run,
            active_records=len(active),
            already_synced=already_synced,
            existing_in_notion=existing_in_notion,
            would_create=would_create,
            migrated=migrated,
            delete_pending=delete_pending,
            deleted_in_notion=deleted_in_notion,
        )

    def _normalize_task(self, task: dict[str, Any]) -> None:
        ensure_iso_datetime(
            task,
            local_key="created_at",
            iso_key="created_at_iso",
        )
        ensure_iso_datetime(
            task,
            local_key="completed_at",
            iso_key="completed_at_iso",
            required=False,
        )

        if not task.get("sync_key"):
            task["sync_key"] = build_sync_key(
                entity="task",
                local_id=task["id"],
                content=task["title"],
                created_at=task["created_at"],
            )

        task.setdefault("notion_page_id", None)
        task.setdefault("notion_sync_status", "pending")

    def _sync_task(
        self,
        task: dict[str, Any],
        tasks: list[dict[str, Any]],
    ) -> None:
        if self.notion_store is None:
            return

        try:
            result = self.notion_store.sync_task(task)
        except NotionError as error:
            logger.warning(
                "Notion task sync remains pending: task_id=%s error=%s",
                task["id"],
                error,
            )
            return
        except Exception as error:
            logger.warning(
                "Unexpected Notion task sync failure: "
                "task_id=%s error_type=%s",
                task["id"],
                type(error).__name__,
            )
            return

        task["notion_page_id"] = result.page_id
        task["notion_sync_status"] = "synced"
        self.local.save(tasks)

    def _trash_task(
        self,
        task: dict[str, Any],
        tasks: list[dict[str, Any]],
    ) -> None:
        if self.notion_store is None or not task.get("notion_page_id"):
            return

        try:
            self.notion_store.trash_page(task["notion_page_id"])
        except NotionError as error:
            logger.warning(
                "Notion task trash remains pending: task_id=%s error=%s",
                task["id"],
                error,
            )
            return
        except Exception as error:
            logger.warning(
                "Unexpected Notion task trash failure: "
                "task_id=%s error_type=%s",
                task["id"],
                type(error).__name__,
            )
            return

        task["notion_sync_status"] = "deleted"
        self.local.save(tasks)

    def _exclude_local_tombstones(
        self,
        notion_tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        deleted_page_ids = {
            canonical_notion_id(task["notion_page_id"])
            for task in self.local.load()
            if task.get("deleted_at") and task.get("notion_page_id")
        }
        return [
            task
            for task in notion_tasks
            if not isinstance(task.get("notion_page_id"), str)
            or canonical_notion_id(task["notion_page_id"])
            not in deleted_page_ids
        ]


def build_task_repository(
    *,
    local_path: Path | None = None,
) -> TaskRepository:
    data_source_id = resolve_tasks_data_source_id()
    notion_store = None

    if config.NOTION_API_TOKEN and data_source_id:
        notion_store = _build_notion_store(
            config.NOTION_API_TOKEN,
            config.NOTION_API_VERSION,
            data_source_id,
        )

    return TaskRepository(
        local_path=local_path or config.TASKS_FILE,
        notion_store=notion_store,
        read_from_notion=config.NOTION_TASKS_READ_ENABLED,
    )


@lru_cache(maxsize=8)
def _build_notion_store(
    api_token: str,
    api_version: str,
    data_source_id: str,
) -> NotionTaskStore:
    return NotionTaskStore(
        client=NotionClient(
            api_token=api_token,
            api_version=api_version,
        ),
        data_source_id=data_source_id,
    )


def _log_notion_fallback(operation: str, error: Exception) -> None:
    logger.warning(
        "Notion task read failed; using Local fallback: "
        "operation=%s error=%s",
        operation,
        error,
    )


def _log_unexpected_fallback(
    operation: str,
    error: Exception,
) -> None:
    logger.warning(
        "Unexpected Notion task read failure; using Local fallback: "
        "operation=%s error_type=%s",
        operation,
        type(error).__name__,
    )
