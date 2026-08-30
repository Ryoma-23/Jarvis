import unittest

from unittest.mock import Mock

from app.integrations.notion_client import NotionClient
from app.integrations.notion_memory_store import (
    MEMORY_DATA_SOURCE_SCHEMA,
    REQUIRED_MEMORY_PROPERTY_TYPES,
)
from scripts.setup_notion_storage import setup_notion_storage


class NotionStorageSetupTests(unittest.TestCase):
    def test_memory_setup_creates_and_validates_initial_data_source(self):
        client = Mock(spec=NotionClient)
        client.create_database.return_value = {"id": "memory-database"}
        client.retrieve_database.return_value = {
            "id": "memory-database",
            "url": "https://www.notion.so/memory-database",
            "data_sources": [{"id": "memory-data-source"}],
        }
        client.retrieve_data_source.return_value = {
            "id": "memory-data-source",
            "properties": {
                name: {"name": name, "type": property_type}
                for name, property_type in REQUIRED_MEMORY_PROPERTY_TYPES.items()
            },
        }

        result = setup_notion_storage(
            client,
            entity="memory",
            parent_page_id="parent-page",
        )

        self.assertTrue(result.created)
        self.assertEqual(result.data_source_id, "memory-data-source")
        client.create_database.assert_called_once_with(
            parent_page_id="parent-page",
            title="JARVIS Memory",
            properties=MEMORY_DATA_SOURCE_SCHEMA,
            is_inline=True,
        )
        client.retrieve_data_source.assert_called_once_with(
            "memory-data-source"
        )


if __name__ == "__main__":
    unittest.main()
