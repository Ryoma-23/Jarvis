import hashlib
import json

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.integrations.notion_store import local_datetime_to_iso


@dataclass(frozen=True)
class MigrationResult:
    entity: str
    dry_run: bool
    active_records: int
    already_synced: int
    existing_in_notion: int
    would_create: int
    migrated: int
    delete_pending: int
    deleted_in_notion: int


class JsonListStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[dict[str, Any]]:
        self.path.parent.mkdir(exist_ok=True)

        if not self.path.exists():
            self.save([])

        with open(self.path, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError(
                f"{self.path.name}のJSON形式が正しくありません。"
            )

        return data

    def save(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(exist_ok=True)

        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)


def active_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [record for record in records if not record.get("deleted_at")]


def next_local_id(records: list[dict[str, Any]]) -> int:
    identifiers = [
        record.get("id")
        for record in records
        if isinstance(record.get("id"), int)
        and not isinstance(record.get("id"), bool)
    ]
    return max(identifiers, default=0) + 1


def build_sync_key(
    *,
    entity: str,
    local_id: int,
    content: str,
    created_at: str,
) -> str:
    source = (
        f"{entity}\0{local_id}\0{created_at}\0{content}"
    ).encode("utf-8")
    digest = hashlib.sha256(source).hexdigest()
    return f"jarvis-{entity}:{local_id}:{digest}"


def ensure_iso_datetime(
    record: dict[str, Any],
    *,
    local_key: str,
    iso_key: str,
    required: bool = True,
) -> None:
    iso_value = record.get(iso_key)

    if isinstance(iso_value, str) and iso_value.strip():
        return

    local_value = record.get(local_key)

    if not isinstance(local_value, str) or not local_value.strip():
        if required:
            raise ValueError(
                f"{local_key}が設定されていません。"
            )

        record[iso_key] = None
        return

    record[iso_key] = local_datetime_to_iso(local_value)


def now_values() -> tuple[str, str]:
    now = datetime.now().astimezone()
    return (
        now.strftime("%Y-%m-%d %H:%M:%S"),
        now.isoformat(timespec="seconds"),
    )
