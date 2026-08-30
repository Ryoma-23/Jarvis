from typing import Any

from app.integrations.notion_client import (
    NotionClient,
    NotionConfigurationError,
    NotionResponseError,
)
from app.integrations.notion_store import (
    BaseNotionDataSourceStore,
    NotionRecordSyncResult,
    extract_date,
    extract_number,
    extract_rich_text,
    extract_status,
    format_local_datetime,
    page_id,
    page_properties,
    page_url,
    rich_text_fragments,
)


TASKS_DATABASE_TITLE = "JARVIS Tasks"
TASK_TITLE_PROPERTY = "Title"
TASK_STATUS_PROPERTY = "Status"
TASK_DUE_DATE_PROPERTY = "Due Date"
TASK_CREATED_AT_PROPERTY = "Created At"
TASK_COMPLETED_AT_PROPERTY = "Completed At"
TASK_LOCAL_ID_PROPERTY = "Jarvis ID"
TASK_SYNC_KEY_PROPERTY = "Sync Key"

NOTION_TASK_STATUS_TODO = "Not started"
NOTION_TASK_STATUS_DONE = "Done"

TASKS_DATA_SOURCE_SCHEMA = {
    TASK_TITLE_PROPERTY: {"title": {}},
    TASK_STATUS_PROPERTY: {"status": {}},
    TASK_DUE_DATE_PROPERTY: {"date": {}},
    TASK_CREATED_AT_PROPERTY: {"date": {}},
    TASK_COMPLETED_AT_PROPERTY: {"date": {}},
    TASK_LOCAL_ID_PROPERTY: {"number": {"format": "number"}},
    TASK_SYNC_KEY_PROPERTY: {"rich_text": {}},
}

REQUIRED_TASK_PROPERTY_TYPES = {
    TASK_TITLE_PROPERTY: "title",
    TASK_STATUS_PROPERTY: "status",
    TASK_DUE_DATE_PROPERTY: "date",
    TASK_CREATED_AT_PROPERTY: "date",
    TASK_COMPLETED_AT_PROPERTY: "date",
    TASK_LOCAL_ID_PROPERTY: "number",
    TASK_SYNC_KEY_PROPERTY: "rich_text",
}


class NotionTaskStore(BaseNotionDataSourceStore):
    def __init__(
        self,
        *,
        client: NotionClient,
        data_source_id: str,
    ):
        super().__init__(
            client=client,
            data_source_id=data_source_id,
            required_property_types=REQUIRED_TASK_PROPERTY_TYPES,
        )

    def list_tasks(
        self,
        status_filter: str = "all",
    ) -> list[dict[str, Any]]:
        filter_body = None

        if status_filter in {"todo", "done"}:
            filter_body = {
                "property": TASK_STATUS_PROPERTY,
                "status": {
                    "equals": _notion_status_name(status_filter)
                },
            }

        pages = self.query_pages(
            filter_body=filter_body,
            sorts=[
                {
                    "property": TASK_CREATED_AT_PROPERTY,
                    "direction": "ascending",
                }
            ],
        )
        return [self.task_from_page(page) for page in pages]

    def search_title(self, keyword: str) -> list[dict[str, Any]]:
        normalized = (keyword or "").strip()

        if not normalized:
            raise NotionConfigurationError(
                "Task検索キーワードが指定されていません。"
            )

        pages = self.query_pages(
            filter_body={
                "property": TASK_TITLE_PROPERTY,
                "title": {"contains": normalized},
            },
            sorts=[
                {
                    "property": TASK_CREATED_AT_PROPERTY,
                    "direction": "ascending",
                }
            ],
        )
        return [self.task_from_page(page) for page in pages]

    def find_by_jarvis_id(self, task_id: int) -> list[dict[str, Any]]:
        return [
            self.task_from_page(page)
            for page in self.find_by_number(
                TASK_LOCAL_ID_PROPERTY,
                task_id,
            )
        ]

    def sync_task(
        self,
        task: dict[str, Any],
    ) -> NotionRecordSyncResult:
        sync_key = _required_record_text(task, "sync_key")
        properties = self._properties_from_task(task)
        mapped_page_id = task.get("notion_page_id")

        if isinstance(mapped_page_id, str) and mapped_page_id.strip():
            self.update_page(mapped_page_id, properties)
            return NotionRecordSyncResult(
                page_id=mapped_page_id.strip(),
                already_existed=True,
            )

        existing_pages = self.find_by_rich_text(
            TASK_SYNC_KEY_PROPERTY,
            sync_key,
        )

        if len(existing_pages) > 1:
            raise NotionResponseError(
                "TaskのSync KeyがNotion上で重複しています。"
            )

        if existing_pages:
            existing_page_id = page_id(existing_pages[0])
            self.update_page(existing_page_id, properties)
            return NotionRecordSyncResult(
                page_id=existing_page_id,
                already_existed=True,
            )

        created_page = self.create_page(properties)
        return NotionRecordSyncResult(
            page_id=page_id(created_page),
            already_existed=False,
        )

    def task_from_page(
        self,
        page: dict[str, Any],
    ) -> dict[str, Any]:
        properties = page_properties(page)
        created_at_iso = extract_date(
            properties,
            TASK_CREATED_AT_PROPERTY,
            required=True,
        )
        completed_at_iso = extract_date(
            properties,
            TASK_COMPLETED_AT_PROPERTY,
        )
        status = _local_status_name(
            extract_status(properties, TASK_STATUS_PROPERTY)
        )
        return {
            "id": extract_number(properties, TASK_LOCAL_ID_PROPERTY),
            "title": extract_rich_text(
                properties,
                TASK_TITLE_PROPERTY,
                value_key="title",
            ),
            "status": status,
            "due_date": extract_date(
                properties,
                TASK_DUE_DATE_PROPERTY,
            ),
            "created_at": format_local_datetime(created_at_iso),
            "created_at_iso": created_at_iso,
            "completed_at": (
                format_local_datetime(completed_at_iso)
                if completed_at_iso
                else None
            ),
            "completed_at_iso": completed_at_iso,
            "sync_key": extract_rich_text(
                properties,
                TASK_SYNC_KEY_PROPERTY,
            ),
            "notion_page_id": page_id(page),
            "notion_sync_status": "synced",
            "notion_url": page_url(page),
        }

    def _properties_from_task(
        self,
        task: dict[str, Any],
    ) -> dict[str, Any]:
        task_id = task.get("id")

        if not isinstance(task_id, int) or isinstance(task_id, bool):
            raise NotionConfigurationError(
                "Taskのidが整数ではありません。"
            )

        status = task.get("status")

        if status not in {"todo", "done"}:
            raise NotionConfigurationError(
                "Taskのstatusはtodoまたはdoneが必要です。"
            )

        due_date = task.get("due_date")
        completed_at_iso = task.get("completed_at_iso")
        return {
            TASK_TITLE_PROPERTY: {
                "title": rich_text_fragments(
                    _required_record_text(task, "title")
                )
            },
            TASK_STATUS_PROPERTY: {
                "status": {"name": _notion_status_name(status)}
            },
            TASK_DUE_DATE_PROPERTY: {
                "date": (
                    {"start": due_date}
                    if isinstance(due_date, str) and due_date.strip()
                    else None
                )
            },
            TASK_CREATED_AT_PROPERTY: {
                "date": {
                    "start": _required_record_text(
                        task,
                        "created_at_iso",
                    )
                }
            },
            TASK_COMPLETED_AT_PROPERTY: {
                "date": (
                    {"start": completed_at_iso}
                    if isinstance(completed_at_iso, str)
                    and completed_at_iso.strip()
                    else None
                )
            },
            TASK_LOCAL_ID_PROPERTY: {"number": task_id},
            TASK_SYNC_KEY_PROPERTY: {
                "rich_text": rich_text_fragments(
                    _required_record_text(task, "sync_key")
                )
            },
        }


def _notion_status_name(status: str) -> str:
    return (
        NOTION_TASK_STATUS_DONE
        if status == "done"
        else NOTION_TASK_STATUS_TODO
    )


def _local_status_name(status: str) -> str:
    if status in {NOTION_TASK_STATUS_DONE, "done"}:
        return "done"

    if status in {NOTION_TASK_STATUS_TODO, "todo", "In progress"}:
        return "todo"

    raise NotionResponseError(
        f"Notion TaskのStatusが不明です: {status}"
    )


def _required_record_text(
    record: dict[str, Any],
    name: str,
) -> str:
    value = record.get(name)

    if not isinstance(value, str) or not value.strip():
        raise NotionConfigurationError(
            f"Taskの{name}が設定されていません。"
        )

    return value.strip()
