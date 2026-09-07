import json

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import NOTION_KNOWLEDGE_SYNC_STATE_FILE
from app.knowledge_sync.registry import canonical_notion_id


STATE_VERSION = 1


class KnowledgeSyncStateError(RuntimeError):
    """Raised when incremental synchronization state cannot be used."""


@dataclass
class KnowledgeSyncState:
    collection_name: str
    embedding_model: str
    embedding_dimensions: int
    pages: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(
        self,
        *,
        page_id: str,
        source_type: str,
        last_edited_time: str,
        chunk_count: int,
        synced_at: str,
    ) -> None:
        self.pages[canonical_notion_id(page_id)] = {
            "page_id": page_id.strip(),
            "source_type": source_type.strip(),
            "last_edited_time": last_edited_time.strip(),
            "chunk_count": chunk_count,
            "synced_at": synced_at,
        }

    def remove(self, page_id: str) -> None:
        self.pages.pop(canonical_notion_id(page_id), None)


class KnowledgeSyncStateStore:
    def __init__(
        self,
        path: str | Path = NOTION_KNOWLEDGE_SYNC_STATE_FILE,
    ):
        self.path = Path(path)

    def load(
        self,
        *,
        collection_name: str,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> KnowledgeSyncState:
        empty = KnowledgeSyncState(
            collection_name=collection_name,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
        )

        if not self.path.exists():
            return empty

        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise KnowledgeSyncStateError(
                "Notion同期状態を読み込めませんでした。"
            ) from error

        if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
            raise KnowledgeSyncStateError(
                "Notion同期状態のversionが不正です。"
            )

        if (
            data.get("collection_name") != collection_name
            or data.get("embedding_model") != embedding_model
            or data.get("embedding_dimensions") != embedding_dimensions
        ):
            return empty

        raw_pages = data.get("pages")

        if not isinstance(raw_pages, dict):
            raise KnowledgeSyncStateError(
                "Notion同期状態のpagesが不正です。"
            )

        pages: dict[str, dict[str, Any]] = {}

        for page_key, record in raw_pages.items():
            if not _valid_record(page_key, record):
                raise KnowledgeSyncStateError(
                    "Notion同期状態に不正なPageが含まれています。"
                )

            pages[page_key] = dict(record)

        empty.pages = pages
        return empty

    def save(self, state: KnowledgeSyncState) -> None:
        data = {
            "version": STATE_VERSION,
            "collection_name": state.collection_name,
            "embedding_model": state.embedding_model,
            "embedding_dimensions": state.embedding_dimensions,
            "pages": state.pages,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(f"{self.path.name}.tmp")

        try:
            with open(temporary_path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")

            temporary_path.replace(self.path)
        except OSError as error:
            raise KnowledgeSyncStateError(
                "Notion同期状態を保存できませんでした。"
            ) from error


def _valid_record(page_key: Any, record: Any) -> bool:
    if not isinstance(page_key, str) or not isinstance(record, dict):
        return False

    page_id = record.get("page_id")
    source_type = record.get("source_type")
    last_edited_time = record.get("last_edited_time")
    chunk_count = record.get("chunk_count")
    synced_at = record.get("synced_at")
    try:
        page_id_matches = (
            isinstance(page_id, str)
            and canonical_notion_id(page_id) == page_key
        )
    except RuntimeError:
        page_id_matches = False

    return (
        page_id_matches
        and isinstance(source_type, str)
        and bool(source_type.strip())
        and isinstance(last_edited_time, str)
        and bool(last_edited_time.strip())
        and isinstance(chunk_count, int)
        and not isinstance(chunk_count, bool)
        and chunk_count >= 0
        and isinstance(synced_at, str)
        and bool(synced_at.strip())
    )
