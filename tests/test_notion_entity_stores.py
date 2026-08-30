import unittest

from unittest.mock import Mock

from app.integrations.notion_client import NotionClient
from app.integrations.notion_memory_store import (
    MEMORY_CATEGORY_PROPERTY,
    MEMORY_CONTENT_PROPERTY,
    MEMORY_CREATED_AT_PROPERTY,
    MEMORY_LOCAL_ID_PROPERTY,
    MEMORY_SYNC_KEY_PROPERTY,
    MEMORY_UPDATED_AT_PROPERTY,
    REQUIRED_MEMORY_PROPERTY_TYPES,
    NotionMemoryStore,
)
from app.integrations.notion_task_store import (
    REQUIRED_TASK_PROPERTY_TYPES,
    TASK_COMPLETED_AT_PROPERTY,
    TASK_CREATED_AT_PROPERTY,
    TASK_DUE_DATE_PROPERTY,
    TASK_LOCAL_ID_PROPERTY,
    TASK_STATUS_PROPERTY,
    TASK_SYNC_KEY_PROPERTY,
    TASK_TITLE_PROPERTY,
    NotionTaskStore,
)


DATA_SOURCE_ID = "11111111-2222-3333-4444-555555555555"


def schema_response(property_types):
    return {
        "id": DATA_SOURCE_ID,
        "properties": {
            name: {"name": name, "type": property_type}
            for name, property_type in property_types.items()
        },
    }


def query_response(results=None):
    return {
        "results": results or [],
        "has_more": False,
        "next_cursor": None,
    }


class NotionTaskStoreTests(unittest.TestCase):
    def test_create_serializes_required_task_properties(self):
        client = Mock(spec=NotionClient)
        client.retrieve_data_source.return_value = schema_response(
            REQUIRED_TASK_PROPERTY_TYPES
        )
        client.query_data_source.return_value = query_response()
        client.create_data_source_page.return_value = {"id": "task-page"}
        store = NotionTaskStore(
            client=client,
            data_source_id=DATA_SOURCE_ID,
        )
        task = {
            "id": 1,
            "title": "テストを書く",
            "status": "todo",
            "due_date": "2026-09-01",
            "created_at_iso": "2026-08-30T12:00:00+09:00",
            "completed_at_iso": None,
            "sync_key": "task-sync-1",
        }

        result = store.sync_task(task)

        properties = client.create_data_source_page.call_args.kwargs[
            "properties"
        ]
        self.assertEqual(result.page_id, "task-page")
        self.assertEqual(
            properties[TASK_STATUS_PROPERTY],
            {"status": {"name": "Not started"}},
        )
        self.assertEqual(
            properties[TASK_DUE_DATE_PROPERTY],
            {"date": {"start": "2026-09-01"}},
        )
        self.assertEqual(
            properties[TASK_COMPLETED_AT_PROPERTY],
            {"date": None},
        )
        self.assertEqual(properties[TASK_LOCAL_ID_PROPERTY], {"number": 1})

    def test_complete_updates_status_and_completed_at_together(self):
        client = Mock(spec=NotionClient)
        client.retrieve_data_source.return_value = schema_response(
            REQUIRED_TASK_PROPERTY_TYPES
        )
        client.query_data_source.return_value = query_response(
            [
                {
                    "id": "task-page",
                    "parent": {
                        "type": "data_source_id",
                        "data_source_id": DATA_SOURCE_ID,
                    },
                }
            ]
        )
        store = NotionTaskStore(
            client=client,
            data_source_id=DATA_SOURCE_ID,
        )
        task = {
            "id": 2,
            "title": "完了Task",
            "status": "done",
            "due_date": None,
            "created_at_iso": "2026-08-30T12:00:00+09:00",
            "completed_at_iso": "2026-08-30T13:00:00+09:00",
            "sync_key": "task-sync-2",
        }

        store.sync_task(task)

        properties = client.update_page.call_args.kwargs["properties"]
        self.assertEqual(
            properties[TASK_STATUS_PROPERTY],
            {"status": {"name": "Done"}},
        )
        self.assertEqual(
            properties[TASK_COMPLETED_AT_PROPERTY],
            {"date": {"start": "2026-08-30T13:00:00+09:00"}},
        )


class NotionMemoryStoreTests(unittest.TestCase):
    def test_create_serializes_required_memory_properties(self):
        client = Mock(spec=NotionClient)
        client.retrieve_data_source.return_value = schema_response(
            REQUIRED_MEMORY_PROPERTY_TYPES
        )
        client.query_data_source.return_value = query_response()
        client.create_data_source_page.return_value = {"id": "memory-page"}
        store = NotionMemoryStore(
            client=client,
            data_source_id=DATA_SOURCE_ID,
        )
        memory = {
            "id": 1,
            "content": "Pythonが好き",
            "category": "preference",
            "created_at_iso": "2026-08-30T12:00:00+09:00",
            "updated_at_iso": "2026-08-30T13:00:00+09:00",
            "sync_key": "memory-sync-1",
        }

        result = store.sync_memory(memory)

        properties = client.create_data_source_page.call_args.kwargs[
            "properties"
        ]
        self.assertEqual(result.page_id, "memory-page")
        self.assertEqual(
            properties[MEMORY_CATEGORY_PROPERTY],
            {"select": {"name": "preference"}},
        )
        self.assertEqual(
            properties[MEMORY_UPDATED_AT_PROPERTY],
            {"date": {"start": "2026-08-30T13:00:00+09:00"}},
        )
        self.assertEqual(
            properties[MEMORY_LOCAL_ID_PROPERTY],
            {"number": 1},
        )


if __name__ == "__main__":
    unittest.main()
