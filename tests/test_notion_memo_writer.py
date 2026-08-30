import json
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

from app import config
from app.integrations.notion_client import (
    NotionClient,
    NotionConfigurationError,
)
from app.integrations.notion_memo_writer import (
    CONTENT_PROPERTY,
    CREATED_AT_PROPERTY,
    LOCAL_ID_PROPERTY,
    NOTES_DATA_SOURCE_SCHEMA,
    SOURCE_PROPERTY,
    SYNC_KEY_PROPERTY,
    TITLE_PROPERTY,
    NotionMemoWriter,
    build_notion_note_sync_key,
)
from app.integrations.notion_resources import (
    load_notion_resources,
    resolve_memory_data_source_id,
    resolve_notes_data_source_id,
    resolve_tasks_data_source_id,
    save_memory_notion_resource,
    save_notes_notion_resource,
    save_tasks_notion_resource,
)
from scripts.setup_notion_notes import setup_notion_notes


def data_source_schema_response():
    return {
        "object": "data_source",
        "id": "data-source-id",
        "parent": {
            "type": "database_id",
            "database_id": "database-id",
        },
        "properties": {
            name: {"name": name, "type": property_type}
            for name, property_type in {
                TITLE_PROPERTY: "title",
                CONTENT_PROPERTY: "rich_text",
                LOCAL_ID_PROPERTY: "number",
                CREATED_AT_PROPERTY: "date",
                SOURCE_PROPERTY: "select",
                SYNC_KEY_PROPERTY: "rich_text",
            }.items()
        },
    }


def note_fixture(content="牛乳を買う"):
    created_at = "2026-08-30 16:30:00"
    return {
        "id": 4,
        "content": content,
        "created_at": created_at,
        "created_at_iso": "2026-08-30T16:30:00+09:00",
        "sync_key": build_notion_note_sync_key(
            note_id=4,
            content=content,
            created_at=created_at,
        ),
        "notion_page_id": None,
        "notion_sync_status": "pending",
    }


class NotionMemoWriterTests(unittest.TestCase):
    def test_schema_is_validated_before_first_write(self):
        client = Mock(spec=NotionClient)
        client.retrieve_data_source.return_value = data_source_schema_response()
        client.query_data_source.return_value = {"results": []}
        client.create_data_source_page.return_value = {"id": "page-id"}
        writer = NotionMemoWriter(
            client=client,
            data_source_id="data-source-id",
        )

        result = writer.sync_note(note_fixture())

        self.assertEqual(result.page_id, "page-id")
        self.assertFalse(result.already_existed)
        client.retrieve_data_source.assert_called_once_with("data-source-id")
        request = client.create_data_source_page.call_args.kwargs
        self.assertEqual(request["data_source_id"], "data-source-id")
        properties = request["properties"]
        self.assertEqual(properties[LOCAL_ID_PROPERTY], {"number": 4})
        self.assertEqual(
            properties[CREATED_AT_PROPERTY],
            {"date": {"start": "2026-08-30T16:30:00+09:00"}},
        )
        self.assertEqual(
            properties[SOURCE_PROPERTY],
            {"select": {"name": "JARVIS"}},
        )
        self.assertEqual(
            properties[CONTENT_PROPERTY]["rich_text"][0]["text"]["content"],
            "牛乳を買う",
        )

    def test_existing_sync_key_prevents_duplicate_page_creation(self):
        client = Mock(spec=NotionClient)
        client.retrieve_data_source.return_value = data_source_schema_response()
        client.query_data_source.return_value = {
            "results": [{"id": "existing-page-id"}]
        }
        writer = NotionMemoWriter(
            client=client,
            data_source_id="data-source-id",
        )

        first = writer.sync_note(note_fixture())
        second = writer.sync_note(note_fixture())

        self.assertTrue(first.already_existed)
        self.assertTrue(second.already_existed)
        self.assertEqual(first.page_id, "existing-page-id")
        client.create_data_source_page.assert_not_called()
        client.retrieve_data_source.assert_called_once_with("data-source-id")

    def test_long_content_is_split_without_losing_text(self):
        content = "あ" * 4500
        client = Mock(spec=NotionClient)
        client.retrieve_data_source.return_value = data_source_schema_response()
        client.query_data_source.return_value = {"results": []}
        client.create_data_source_page.return_value = {"id": "page-id"}
        writer = NotionMemoWriter(
            client=client,
            data_source_id="data-source-id",
        )

        writer.sync_note(note_fixture(content))

        fragments = client.create_data_source_page.call_args.kwargs[
            "properties"
        ][CONTENT_PROPERTY]["rich_text"]
        self.assertEqual(len(fragments), 3)
        self.assertEqual(
            "".join(item["text"]["content"] for item in fragments),
            content,
        )

    def test_schema_mismatch_stops_notion_write(self):
        response = data_source_schema_response()
        response["properties"][SYNC_KEY_PROPERTY]["type"] = "number"
        client = Mock(spec=NotionClient)
        client.retrieve_data_source.return_value = response
        writer = NotionMemoWriter(
            client=client,
            data_source_id="data-source-id",
        )

        with self.assertRaisesRegex(
            NotionConfigurationError,
            "Sync Key",
        ):
            writer.sync_note(note_fixture())

        client.query_data_source.assert_not_called()
        client.create_data_source_page.assert_not_called()


class NotionNotesSetupTests(unittest.TestCase):
    def test_setup_creates_database_and_validates_initial_data_source(self):
        client = Mock(spec=NotionClient)
        client.create_database.return_value = {"id": "database-id"}
        client.retrieve_database.return_value = {
            "id": "database-id",
            "url": "https://www.notion.so/database-id",
            "data_sources": [
                {"id": "data-source-id", "name": "JARVIS Notes"}
            ],
        }
        client.retrieve_data_source.return_value = data_source_schema_response()

        result = setup_notion_notes(
            client,
            parent_page_id="parent-page-id",
        )

        self.assertTrue(result.created)
        self.assertEqual(result.data_source_id, "data-source-id")
        client.create_database.assert_called_once_with(
            parent_page_id="parent-page-id",
            title="JARVIS Notes",
            properties=NOTES_DATA_SOURCE_SCHEMA,
            is_inline=True,
        )
        client.retrieve_data_source.assert_called_once_with("data-source-id")

    def test_resource_file_round_trip_and_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notion_resources.json"
            save_notes_notion_resource(
                database_id="database-id",
                data_source_id="data-source-id",
                path=path,
            )

            self.assertEqual(
                load_notion_resources(path),
                {
                    "notes_database_id": "database-id",
                    "notes_data_source_id": "data-source-id",
                },
            )

            with (
                patch.object(config, "NOTION_NOTES_DATA_SOURCE_ID", None),
                patch.object(config, "NOTION_RESOURCES_FILE", path),
            ):
                self.assertEqual(
                    resolve_notes_data_source_id(),
                    "data-source-id",
                )

            with patch.object(
                config,
                "NOTION_NOTES_DATA_SOURCE_ID",
                "environment-data-source-id",
            ):
                self.assertEqual(
                    resolve_notes_data_source_id(),
                    "environment-data-source-id",
                )

    def test_task_and_memory_resource_ids_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notion_resources.json"
            save_tasks_notion_resource(
                database_id="tasks-database",
                data_source_id="tasks-data-source",
                path=path,
            )
            save_memory_notion_resource(
                database_id="memory-database",
                data_source_id="memory-data-source",
                path=path,
            )

            with (
                patch.object(config, "NOTION_RESOURCES_FILE", path),
                patch.object(config, "NOTION_TASKS_DATA_SOURCE_ID", None),
                patch.object(config, "NOTION_MEMORY_DATA_SOURCE_ID", None),
            ):
                self.assertEqual(
                    resolve_tasks_data_source_id(),
                    "tasks-data-source",
                )
                self.assertEqual(
                    resolve_memory_data_source_id(),
                    "memory-data-source",
                )


if __name__ == "__main__":
    unittest.main()
