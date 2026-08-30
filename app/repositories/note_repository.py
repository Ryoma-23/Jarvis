import logging

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from app import config
from app.integrations.notion_client import NotionClient, NotionError
from app.integrations.notion_memo_reader import NotionMemoReader
from app.integrations.notion_memo_writer import (
    NotionMemoWriter,
    build_notion_note_sync_key,
)
from app.integrations.notion_resources import (
    resolve_notes_data_source_id,
)
from app.integrations.notion_store import canonical_notion_id
from app.repositories.common import (
    JsonListStore,
    MigrationResult,
    active_records,
    ensure_iso_datetime,
    next_local_id,
    now_values,
)


logger = logging.getLogger(__name__)


class NoteRepository:
    def __init__(
        self,
        *,
        local_path: Path,
        notion_writer: NotionMemoWriter | None,
        notion_reader: NotionMemoReader | None,
        read_from_notion: bool,
    ):
        self.local = JsonListStore(local_path)
        self.notion_writer = notion_writer
        self.notion_reader = notion_reader
        self.read_from_notion = read_from_notion

    def load_all_local(self) -> list[dict[str, Any]]:
        return self.local.load()

    def save_all_local(self, notes: list[dict[str, Any]]) -> None:
        self.local.save(notes)

    def add(self, content: str) -> dict[str, Any]:
        notes = self.local.load()
        note_id = next_local_id(notes)
        created_at, created_at_iso = now_values()
        note = {
            "id": note_id,
            "content": content,
            "created_at": created_at,
            "created_at_iso": created_at_iso,
            "sync_key": build_notion_note_sync_key(
                note_id=note_id,
                content=content,
                created_at=created_at,
            ),
            "notion_page_id": None,
            "notion_sync_status": "pending",
        }
        notes.append(note)
        self.local.save(notes)
        self._sync_note(note, notes)
        return note

    def list(self) -> list[dict[str, Any]]:
        if self.read_from_notion and self.notion_reader is not None:
            try:
                return self._exclude_local_tombstones(
                    self.notion_reader.list_notes()
                )
            except NotionError as error:
                _log_notion_fallback("list", error)
            except Exception as error:
                _log_unexpected_fallback("list", error)

        return active_records(self.local.load())

    def search(self, keyword: str) -> list[dict[str, Any]]:
        if self.read_from_notion and self.notion_reader is not None:
            try:
                return self._exclude_local_tombstones(
                    self.notion_reader.search_content(keyword)
                )
            except NotionError as error:
                _log_notion_fallback("search", error)
            except Exception as error:
                _log_unexpected_fallback("search", error)

        lowered = keyword.lower()
        return [
            note
            for note in active_records(self.local.load())
            if lowered in note["content"].lower()
        ]

    def get_by_local_id(self, note_id: int) -> dict[str, Any] | None:
        if self.read_from_notion and self.notion_reader is not None:
            try:
                return self.notion_reader.get_by_local_id(note_id)
            except NotionError as error:
                _log_notion_fallback("local_id", error)
            except Exception as error:
                _log_unexpected_fallback("local_id", error)

        return next(
            (
                note
                for note in active_records(self.local.load())
                if note.get("id") == note_id
            ),
            None,
        )

    def get_by_page_id(self, page_id: str) -> dict[str, Any] | None:
        if self.read_from_notion and self.notion_reader is not None:
            try:
                return self.notion_reader.get_by_page_id(page_id)
            except NotionError as error:
                _log_notion_fallback("page_id", error)
            except Exception as error:
                _log_unexpected_fallback("page_id", error)

        return next(
            (
                note
                for note in active_records(self.local.load())
                if note.get("notion_page_id") == page_id
            ),
            None,
        )

    def delete(self, note_ids: list[int]) -> list[int]:
        notes = self.local.load()
        targets = [
            note
            for note in active_records(notes)
            if note.get("id") in note_ids
        ]

        if not targets:
            return []

        deleted_at, deleted_at_iso = now_values()

        for note in targets:
            note["deleted_at"] = deleted_at
            note["deleted_at_iso"] = deleted_at_iso
            note["notion_sync_status"] = (
                "delete_pending"
                if note.get("notion_page_id")
                else "deleted"
            )

        self.local.save(notes)

        for note in targets:
            self._trash_note(note, notes)

        return [note["id"] for note in targets]

    def delete_all(self) -> list[int]:
        return self.delete(
            [note["id"] for note in active_records(self.local.load())]
        )

    def migrate(self, *, dry_run: bool) -> MigrationResult:
        if self.notion_writer is None:
            raise ValueError("Notes用Notion Repositoryが設定されていません。")

        self.notion_writer.validate_schema()
        notes = self.local.load()
        active = active_records(notes)
        already_synced = 0
        existing_in_notion = 0
        would_create = 0
        migrated = 0
        delete_pending = 0
        deleted_in_notion = 0

        for stored_note in active:
            note = deepcopy(stored_note)
            self._normalize_note(note)
            existing_page_id = self.notion_writer.find_page_id_by_sync_key(
                note["sync_key"]
            )

            if existing_page_id:
                existing_in_notion += 1
            else:
                would_create += 1

            if (
                stored_note.get("notion_sync_status") == "synced"
                and stored_note.get("notion_page_id")
            ):
                already_synced += 1

            if dry_run:
                continue

            result = self.notion_writer.sync_note(note)
            stored_note.update(note)
            stored_note["notion_page_id"] = result.page_id
            stored_note["notion_sync_status"] = "synced"
            migrated += 1

        for note in notes:
            if note.get("notion_sync_status") != "delete_pending":
                continue

            delete_pending += 1

            if dry_run:
                continue

            self.notion_writer.trash_page(note["notion_page_id"])
            note["notion_sync_status"] = "deleted"
            deleted_in_notion += 1

        if not dry_run:
            self.local.save(notes)

        return MigrationResult(
            entity="notes",
            dry_run=dry_run,
            active_records=len(active),
            already_synced=already_synced,
            existing_in_notion=existing_in_notion,
            would_create=would_create,
            migrated=migrated,
            delete_pending=delete_pending,
            deleted_in_notion=deleted_in_notion,
        )

    def _normalize_note(self, note: dict[str, Any]) -> None:
        ensure_iso_datetime(
            note,
            local_key="created_at",
            iso_key="created_at_iso",
        )
        if not note.get("sync_key"):
            note["sync_key"] = build_notion_note_sync_key(
                note_id=note["id"],
                content=note["content"],
                created_at=note["created_at"],
            )
        note.setdefault("notion_page_id", None)
        note.setdefault("notion_sync_status", "pending")

    def _sync_note(
        self,
        note: dict[str, Any],
        notes: list[dict[str, Any]],
    ) -> None:
        if self.notion_writer is None:
            return

        try:
            result = self.notion_writer.sync_note(note)
        except NotionError as error:
            logger.warning(
                "Notion note sync remains pending: note_id=%s error=%s",
                note["id"],
                error,
            )
            return
        except Exception as error:
            logger.warning(
                "Unexpected Notion note sync failure: "
                "note_id=%s error_type=%s",
                note["id"],
                type(error).__name__,
            )
            return

        note["notion_page_id"] = result.page_id
        note["notion_sync_status"] = "synced"
        self.local.save(notes)

    def _trash_note(
        self,
        note: dict[str, Any],
        notes: list[dict[str, Any]],
    ) -> None:
        if (
            self.notion_writer is None
            or not note.get("notion_page_id")
        ):
            return

        try:
            self.notion_writer.trash_page(note["notion_page_id"])
        except NotionError as error:
            logger.warning(
                "Notion note trash remains pending: note_id=%s error=%s",
                note["id"],
                error,
            )
            return
        except Exception as error:
            logger.warning(
                "Unexpected Notion note trash failure: "
                "note_id=%s error_type=%s",
                note["id"],
                type(error).__name__,
            )
            return

        note["notion_sync_status"] = "deleted"
        self.local.save(notes)

    def _exclude_local_tombstones(
        self,
        notion_notes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        deleted_page_ids = {
            canonical_notion_id(note["notion_page_id"])
            for note in self.local.load()
            if note.get("deleted_at") and note.get("notion_page_id")
        }
        return [
            note
            for note in notion_notes
            if not isinstance(note.get("notion_page_id"), str)
            or canonical_notion_id(note["notion_page_id"])
            not in deleted_page_ids
        ]


def build_note_repository(
    *,
    local_path: Path | None = None,
) -> NoteRepository:
    data_source_id = resolve_notes_data_source_id()
    writer = None
    reader = None

    if config.NOTION_API_TOKEN and data_source_id:
        writer, reader = _build_notion_adapters(
            config.NOTION_API_TOKEN,
            config.NOTION_API_VERSION,
            data_source_id,
        )

    return NoteRepository(
        local_path=local_path or config.NOTES_FILE,
        notion_writer=writer,
        notion_reader=reader,
        read_from_notion=config.NOTION_NOTES_READ_ENABLED,
    )


@lru_cache(maxsize=8)
def _build_notion_adapters(
    api_token: str,
    api_version: str,
    data_source_id: str,
) -> tuple[NotionMemoWriter, NotionMemoReader]:
    client = NotionClient(
        api_token=api_token,
        api_version=api_version,
    )
    return (
        NotionMemoWriter(
            client=client,
            data_source_id=data_source_id,
        ),
        NotionMemoReader(
            client=client,
            data_source_id=data_source_id,
        ),
    )


def _log_notion_fallback(operation: str, error: Exception) -> None:
    logger.warning(
        "Notion note read failed; using Local fallback: "
        "operation=%s error=%s",
        operation,
        error,
    )


def _log_unexpected_fallback(
    operation: str,
    error: Exception,
) -> None:
    logger.warning(
        "Unexpected Notion note read failure; using Local fallback: "
        "operation=%s error_type=%s",
        operation,
        type(error).__name__,
    )
