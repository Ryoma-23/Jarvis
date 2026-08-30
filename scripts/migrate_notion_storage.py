import argparse
import sys

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.integrations.notion_client import NotionError  # noqa: E402
from app.repositories.memory_repository import (  # noqa: E402
    build_memory_repository,
)
from app.repositories.note_repository import (  # noqa: E402
    build_note_repository,
)
from app.repositories.task_repository import (  # noqa: E402
    build_task_repository,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Local JSONをNotionへ重複なく移行し、delete_pendingも再試行します。"
        )
    )
    parser.add_argument(
        "--entity",
        choices=("notes", "tasks", "memory", "all"),
        default="all",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="変更を加えず移行内容を確認します（既定）。",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Notionへの作成・更新とLocal対応IDの保存を実行します。",
    )
    arguments = parser.parse_args()
    dry_run = not arguments.apply
    entities = (
        ("notes", "tasks", "memory")
        if arguments.entity == "all"
        else (arguments.entity,)
    )
    repositories = {
        "notes": build_note_repository,
        "tasks": build_task_repository,
        "memory": build_memory_repository,
    }

    try:
        results = [
            repositories[entity]().migrate(dry_run=dry_run)
            for entity in entities
        ]
    except (NotionError, ValueError) as error:
        print(f"Notion Storage移行に失敗しました: {error}", file=sys.stderr)
        return 1

    print("DRY RUN" if dry_run else "APPLY")

    for result in results:
        print(
            f"{result.entity}: active={result.active_records}, "
            f"already_synced={result.already_synced}, "
            f"existing_in_notion={result.existing_in_notion}, "
            f"would_create={result.would_create}, "
            f"migrated={result.migrated}, "
            f"delete_pending={result.delete_pending}, "
            f"deleted_in_notion={result.deleted_in_notion}"
        )

    if dry_run:
        print("変更は行っていません。実行する場合は--applyを指定してください。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
