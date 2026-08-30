import sys

from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.config import NOTION_API_TOKEN, NOTION_API_VERSION  # noqa: E402
from app.integrations.notion_client import (  # noqa: E402
    NotionClient,
    NotionError,
)
from app.integrations.notion_memory_store import (  # noqa: E402
    NotionMemoryStore,
)
from app.integrations.notion_memo_reader import NotionMemoReader  # noqa: E402
from app.integrations.notion_memo_writer import (  # noqa: E402
    NotionMemoWriter,
    build_notion_note_sync_key,
)
from app.integrations.notion_resources import (  # noqa: E402
    resolve_memory_data_source_id,
    resolve_notes_data_source_id,
    resolve_tasks_data_source_id,
)
from app.integrations.notion_task_store import NotionTaskStore  # noqa: E402
from app.repositories.common import build_sync_key  # noqa: E402


class StorageCrudVerificationError(NotionError):
    """Raised when a real Notion CRUD verification step fails."""


def verify_notion_storage_crud() -> dict[str, str]:
    notes_data_source_id = _require_id(
        resolve_notes_data_source_id(),
        "Notes",
    )
    tasks_data_source_id = _require_id(
        resolve_tasks_data_source_id(),
        "Tasks",
    )
    memory_data_source_id = _require_id(
        resolve_memory_data_source_id(),
        "Memory",
    )
    client = NotionClient(
        api_token=NOTION_API_TOKEN,
        api_version=NOTION_API_VERSION,
    )
    note_writer = NotionMemoWriter(
        client=client,
        data_source_id=notes_data_source_id,
    )
    note_reader = NotionMemoReader(
        client=client,
        data_source_id=notes_data_source_id,
    )
    task_store = NotionTaskStore(
        client=client,
        data_source_id=tasks_data_source_id,
    )
    memory_store = NotionMemoryStore(
        client=client,
        data_source_id=memory_data_source_id,
    )
    now = datetime.now().astimezone()
    local_id = int(now.timestamp())
    created_at = now.strftime("%Y-%m-%d %H:%M:%S")
    created_at_iso = now.isoformat(timespec="seconds")
    page_ids = {}

    try:
        note_content = f"JARVIS Phase 4 CRUD Test {created_at_iso}"
        note = {
            "id": local_id,
            "content": note_content,
            "created_at": created_at,
            "created_at_iso": created_at_iso,
            "sync_key": build_notion_note_sync_key(
                note_id=local_id,
                content=note_content,
                created_at=created_at,
            ),
        }
        note_result = note_writer.sync_note(note)
        page_ids["notes"] = note_result.page_id
        read_note = note_reader.get_by_page_id(note_result.page_id)

        if read_note["content"] != note_content:
            raise StorageCrudVerificationError(
                "MemoのCreate / Retrieve結果が一致しません。"
            )

        note_trash = note_writer.trash_page(note_result.page_id)
        _verify_in_trash(note_trash, "Memo")

        task = {
            "id": local_id,
            "title": f"JARVIS Phase 4 Task CRUD Test {created_at_iso}",
            "status": "todo",
            "due_date": now.date().isoformat(),
            "created_at": created_at,
            "created_at_iso": created_at_iso,
            "completed_at": None,
            "completed_at_iso": None,
            "sync_key": build_sync_key(
                entity="task",
                local_id=local_id,
                content="Phase 4 Task CRUD",
                created_at=created_at,
            ),
            "notion_page_id": None,
        }
        task_result = task_store.sync_task(task)
        page_ids["tasks"] = task_result.page_id
        task["notion_page_id"] = task_result.page_id
        task["status"] = "done"
        task["completed_at"] = created_at
        task["completed_at_iso"] = created_at_iso
        task_store.sync_task(task)
        read_task = task_store.task_from_page(
            task_store.retrieve_page(task_result.page_id)
        )

        if read_task["status"] != "done" or not read_task["completed_at"]:
            raise StorageCrudVerificationError(
                "TaskのStatus / Completed At更新を取得できません。"
            )

        task_trash = task_store.trash_page(task_result.page_id)
        _verify_in_trash(task_trash, "Task")

        memory = {
            "id": local_id,
            "content": f"JARVIS Phase 4 Memory CRUD Test {created_at_iso}",
            "category": "other",
            "created_at": created_at,
            "created_at_iso": created_at_iso,
            "updated_at": created_at,
            "updated_at_iso": created_at_iso,
            "sync_key": build_sync_key(
                entity="memory",
                local_id=local_id,
                content="Phase 4 Memory CRUD",
                created_at=created_at,
            ),
            "notion_page_id": None,
        }
        memory_result = memory_store.sync_memory(memory)
        page_ids["memory"] = memory_result.page_id
        memory["notion_page_id"] = memory_result.page_id
        memory["content"] += " updated"
        memory_store.sync_memory(memory)
        read_memory = memory_store.memory_from_page(
            memory_store.retrieve_page(memory_result.page_id)
        )

        if read_memory["content"] != memory["content"]:
            raise StorageCrudVerificationError(
                "Memoryの更新内容を取得できません。"
            )

        memory_trash = memory_store.trash_page(memory_result.page_id)
        _verify_in_trash(memory_trash, "Memory")
    except Exception:
        _trash_safely(client, page_ids.values())
        raise

    return page_ids


def main() -> int:
    try:
        page_ids = verify_notion_storage_crud()
    except NotionError as error:
        print(f"Notion Storage CRUD確認に失敗しました: {error}", file=sys.stderr)
        return 1

    print("Notion Storage CRUD確認に成功しました。")

    for entity, page_id in page_ids.items():
        print(f"{entity} Page ID: {page_id} (in trash)")

    return 0


def _require_id(value: str | None, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StorageCrudVerificationError(
            f"{name}用Data Source IDが設定されていません。"
        )

    return value.strip()


def _verify_in_trash(page: dict, entity: str) -> None:
    if page.get("in_trash") is not True:
        raise StorageCrudVerificationError(
            f"{entity} PageがTrashへ移動していません。"
        )


def _trash_safely(client: NotionClient, page_ids) -> None:
    for page_id in page_ids:
        try:
            client.update_page(page_id, in_trash=True)
        except NotionError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
