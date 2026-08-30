import argparse
import sys

from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.integrations.notion_client import NotionError  # noqa: E402
from app.repositories.common import active_records  # noqa: E402
from app.repositories.memory_repository import (  # noqa: E402
    build_memory_repository,
)
from app.repositories.task_repository import (  # noqa: E402
    build_task_repository,
)


class StorageVerificationError(NotionError):
    """Raised when Local/Notion storage records do not match."""


def verify_entity(entity: str) -> tuple[int, int, int]:
    if entity == "tasks":
        repository = build_task_repository()

        if repository.notion_store is None:
            raise StorageVerificationError(
                "Tasks用Notion Repositoryが設定されていません。"
            )

        local_records = active_records(repository.load_all_local())
        notion_records = repository.notion_store.list_tasks()
        fields = ("id", "title", "status", "due_date", "sync_key")
        date_fields = (
            ("created_at_iso", True),
            ("completed_at_iso", False),
        )
    elif entity == "memory":
        repository = build_memory_repository()

        if repository.notion_store is None:
            raise StorageVerificationError(
                "Memory用Notion Repositoryが設定されていません。"
            )

        local_records = active_records(repository.load_all_local())
        notion_records = repository.notion_store.list_memories()
        fields = ("id", "content", "category", "sync_key")
        date_fields = (
            ("created_at_iso", True),
            ("updated_at_iso", True),
        )
    else:
        raise StorageVerificationError(f"未対応のentityです: {entity}")

    local_by_page = _index_by_page_id(local_records, "Local")
    notion_by_page = _index_by_page_id(notion_records, "Notion")
    matched_page_ids = local_by_page.keys() & notion_by_page.keys()

    if len(matched_page_ids) != len(local_records):
        raise StorageVerificationError(
            f"{entity}: Local追跡PageをNotionからすべて取得できません: "
            f"local={len(local_records)}, matched={len(matched_page_ids)}"
        )

    for page_id in matched_page_ids:
        local_record = local_by_page[page_id]
        notion_record = notion_by_page[page_id]

        for field in fields:
            if local_record.get(field) != notion_record.get(field):
                raise StorageVerificationError(
                    f"{entity} {local_record.get('id')} の{field}が一致しません。"
                )

        for field, required in date_fields:
            _verify_datetime(
                local_record.get(field),
                notion_record.get(field),
                field,
                required=required,
            )

    return (
        len(local_records),
        len(matched_page_ids),
        len(notion_records) - len(matched_page_ids),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Task / MemoryのLocal・Notion主要フィールドを比較します。"
    )
    parser.add_argument(
        "--entity",
        choices=("tasks", "memory", "all"),
        default="all",
    )
    arguments = parser.parse_args()
    entities = (
        ("tasks", "memory")
        if arguments.entity == "all"
        else (arguments.entity,)
    )

    try:
        results = {
            entity: verify_entity(entity)
            for entity in entities
        }
    except (NotionError, ValueError) as error:
        print(f"Notion Storage比較に失敗しました: {error}", file=sys.stderr)
        return 1

    for entity, (local_count, matched_count, extra_count) in results.items():
        print(
            f"{entity}: local={local_count}, matched={matched_count}, "
            f"untracked_notion={extra_count}"
        )

    print("Local・Notion Storage比較に成功しました。")
    return 0


def _index_by_page_id(records, source):
    indexed = {}

    for record in records:
        page_id = record.get("notion_page_id")

        if not isinstance(page_id, str) or not page_id.strip():
            raise StorageVerificationError(
                f"{source} record {record.get('id')} にPage IDがありません。"
            )

        canonical = page_id.replace("-", "").lower()

        if canonical in indexed:
            raise StorageVerificationError(
                f"{source}のPage ID {page_id} が重複しています。"
            )

        indexed[canonical] = record

    return indexed


def _verify_datetime(
    local_value,
    notion_value,
    field,
    *,
    required,
):
    if local_value is None and notion_value is None and not required:
        return

    if not isinstance(local_value, str) or not isinstance(notion_value, str):
        raise StorageVerificationError(f"{field}を比較できません。")

    try:
        local_datetime = datetime.fromisoformat(
            local_value.replace("Z", "+00:00")
        )
        notion_datetime = datetime.fromisoformat(
            notion_value.replace("Z", "+00:00")
        )
    except ValueError:
        raise StorageVerificationError(
            f"{field}が有効なISO日時ではありません。"
        ) from None

    if (
        local_datetime.replace(second=0, microsecond=0)
        != notion_datetime.replace(second=0, microsecond=0)
    ):
        raise StorageVerificationError(
            f"{field}が分単位で一致しません。"
        )


if __name__ == "__main__":
    raise SystemExit(main())
