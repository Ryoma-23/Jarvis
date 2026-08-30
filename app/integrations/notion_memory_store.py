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
    extract_select,
    format_local_datetime,
    page_id,
    page_properties,
    page_url,
    rich_text_fragments,
)


MEMORY_DATABASE_TITLE = "JARVIS Memory"
MEMORY_CONTENT_PROPERTY = "Content"
MEMORY_CATEGORY_PROPERTY = "Category"
MEMORY_CREATED_AT_PROPERTY = "Created At"
MEMORY_UPDATED_AT_PROPERTY = "Updated At"
MEMORY_LOCAL_ID_PROPERTY = "Jarvis ID"
MEMORY_SYNC_KEY_PROPERTY = "Sync Key"

MEMORY_DATA_SOURCE_SCHEMA = {
    MEMORY_CONTENT_PROPERTY: {"title": {}},
    MEMORY_CATEGORY_PROPERTY: {
        "select": {
            "options": [
                {"name": "other", "color": "gray"},
                {"name": "profile", "color": "blue"},
                {"name": "preference", "color": "green"},
                {"name": "goal", "color": "yellow"},
                {"name": "project", "color": "purple"},
                {"name": "routine", "color": "orange"},
            ]
        }
    },
    MEMORY_CREATED_AT_PROPERTY: {"date": {}},
    MEMORY_UPDATED_AT_PROPERTY: {"date": {}},
    MEMORY_LOCAL_ID_PROPERTY: {"number": {"format": "number"}},
    MEMORY_SYNC_KEY_PROPERTY: {"rich_text": {}},
}

REQUIRED_MEMORY_PROPERTY_TYPES = {
    MEMORY_CONTENT_PROPERTY: "title",
    MEMORY_CATEGORY_PROPERTY: "select",
    MEMORY_CREATED_AT_PROPERTY: "date",
    MEMORY_UPDATED_AT_PROPERTY: "date",
    MEMORY_LOCAL_ID_PROPERTY: "number",
    MEMORY_SYNC_KEY_PROPERTY: "rich_text",
}


class NotionMemoryStore(BaseNotionDataSourceStore):
    def __init__(
        self,
        *,
        client: NotionClient,
        data_source_id: str,
    ):
        super().__init__(
            client=client,
            data_source_id=data_source_id,
            required_property_types=REQUIRED_MEMORY_PROPERTY_TYPES,
        )

    def list_memories(self) -> list[dict[str, Any]]:
        pages = self.query_pages(
            sorts=[
                {
                    "property": MEMORY_CREATED_AT_PROPERTY,
                    "direction": "ascending",
                }
            ]
        )
        return [self.memory_from_page(page) for page in pages]

    def search_memories(self, keyword: str) -> list[dict[str, Any]]:
        normalized = (keyword or "").strip()

        if not normalized:
            raise NotionConfigurationError(
                "Memory検索キーワードが指定されていません。"
            )

        lowered = normalized.lower()
        return [
            memory
            for memory in self.list_memories()
            if lowered in memory["content"].lower()
            or lowered in memory["category"].lower()
        ]

    def find_by_jarvis_id(self, memory_id: int) -> list[dict[str, Any]]:
        return [
            self.memory_from_page(page)
            for page in self.find_by_number(
                MEMORY_LOCAL_ID_PROPERTY,
                memory_id,
            )
        ]

    def sync_memory(
        self,
        memory: dict[str, Any],
    ) -> NotionRecordSyncResult:
        sync_key = _required_record_text(memory, "sync_key")
        properties = self._properties_from_memory(memory)
        mapped_page_id = memory.get("notion_page_id")

        if isinstance(mapped_page_id, str) and mapped_page_id.strip():
            self.update_page(mapped_page_id, properties)
            return NotionRecordSyncResult(
                page_id=mapped_page_id.strip(),
                already_existed=True,
            )

        existing_pages = self.find_by_rich_text(
            MEMORY_SYNC_KEY_PROPERTY,
            sync_key,
        )

        if len(existing_pages) > 1:
            raise NotionResponseError(
                "MemoryのSync KeyがNotion上で重複しています。"
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

    def memory_from_page(
        self,
        page: dict[str, Any],
    ) -> dict[str, Any]:
        properties = page_properties(page)
        created_at_iso = extract_date(
            properties,
            MEMORY_CREATED_AT_PROPERTY,
            required=True,
        )
        updated_at_iso = extract_date(
            properties,
            MEMORY_UPDATED_AT_PROPERTY,
            required=True,
        )
        return {
            "id": extract_number(properties, MEMORY_LOCAL_ID_PROPERTY),
            "content": extract_rich_text(
                properties,
                MEMORY_CONTENT_PROPERTY,
                value_key="title",
            ),
            "category": extract_select(
                properties,
                MEMORY_CATEGORY_PROPERTY,
            ),
            "created_at": format_local_datetime(created_at_iso),
            "created_at_iso": created_at_iso,
            "updated_at": format_local_datetime(updated_at_iso),
            "updated_at_iso": updated_at_iso,
            "sync_key": extract_rich_text(
                properties,
                MEMORY_SYNC_KEY_PROPERTY,
            ),
            "notion_page_id": page_id(page),
            "notion_sync_status": "synced",
            "notion_url": page_url(page),
        }

    def _properties_from_memory(
        self,
        memory: dict[str, Any],
    ) -> dict[str, Any]:
        memory_id = memory.get("id")

        if not isinstance(memory_id, int) or isinstance(memory_id, bool):
            raise NotionConfigurationError(
                "Memoryのidが整数ではありません。"
            )

        return {
            MEMORY_CONTENT_PROPERTY: {
                "title": rich_text_fragments(
                    _required_record_text(memory, "content")
                )
            },
            MEMORY_CATEGORY_PROPERTY: {
                "select": {
                    "name": _required_record_text(memory, "category")
                }
            },
            MEMORY_CREATED_AT_PROPERTY: {
                "date": {
                    "start": _required_record_text(
                        memory,
                        "created_at_iso",
                    )
                }
            },
            MEMORY_UPDATED_AT_PROPERTY: {
                "date": {
                    "start": _required_record_text(
                        memory,
                        "updated_at_iso",
                    )
                }
            },
            MEMORY_LOCAL_ID_PROPERTY: {"number": memory_id},
            MEMORY_SYNC_KEY_PROPERTY: {
                "rich_text": rich_text_fragments(
                    _required_record_text(memory, "sync_key")
                )
            },
        }


def _required_record_text(
    record: dict[str, Any],
    name: str,
) -> str:
    value = record.get(name)

    if not isinstance(value, str) or not value.strip():
        raise NotionConfigurationError(
            f"Memoryの{name}が設定されていません。"
        )

    return value.strip()
