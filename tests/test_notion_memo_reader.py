import unittest

from datetime import datetime
from unittest.mock import Mock, call

from app.integrations.notion_client import (
    NotionClient,
    NotionResponseError,
)
from app.integrations.notion_memo_reader import (
    CREATED_AT_ASCENDING_SORT,
    NotionMemoReader,
)
from app.integrations.notion_memo_writer import (
    CONTENT_PROPERTY,
    CREATED_AT_PROPERTY,
    LOCAL_ID_PROPERTY,
    SOURCE_PROPERTY,
    SYNC_KEY_PROPERTY,
    TITLE_PROPERTY,
)


DATA_SOURCE_ID = "11111111-2222-3333-4444-555555555555"


def data_source_schema_response():
    return {
        "object": "data_source",
        "id": DATA_SOURCE_ID,
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


def page_fixture(
    note_id,
    content,
    *,
    created_at_iso="2026-08-30T16:30:00+09:00",
):
    return {
        "object": "page",
        "id": f"page-{note_id}",
        "last_edited_time": "2026-08-30T08:00:00.000Z",
        "parent": {
            "type": "data_source_id",
            "data_source_id": DATA_SOURCE_ID.replace("-", ""),
        },
        "url": f"https://www.notion.so/page-{note_id}",
        "properties": {
            TITLE_PROPERTY: {
                "id": "title",
                "type": "title",
                "title": [{"plain_text": content[:100]}],
            },
            CONTENT_PROPERTY: {
                "id": "content-property-id",
                "type": "rich_text",
                "rich_text": [
                    {"plain_text": content[:2]},
                    {"plain_text": content[2:]},
                ],
            },
            LOCAL_ID_PROPERTY: {
                "type": "number",
                "number": note_id,
            },
            CREATED_AT_PROPERTY: {
                "type": "date",
                "date": {"start": created_at_iso},
            },
            SOURCE_PROPERTY: {
                "type": "select",
                "select": {"name": "JARVIS"},
            },
            SYNC_KEY_PROPERTY: {
                "type": "rich_text",
                "rich_text": [{"plain_text": f"sync-{note_id}"}],
            },
        },
    }


def reader_with_client():
    client = Mock(spec=NotionClient)
    client.retrieve_data_source.return_value = data_source_schema_response()
    return (
        NotionMemoReader(
            client=client,
            data_source_id=DATA_SOURCE_ID,
        ),
        client,
    )


class NotionMemoReaderTests(unittest.TestCase):
    def test_list_follows_every_cursor_and_sorts_by_created_at(self):
        reader, client = reader_with_client()
        client.query_data_source.side_effect = (
            {
                "results": [
                    page_fixture(
                        1,
                        "最初のメモ",
                        created_at_iso="2026-08-30T10:00:00+09:00",
                    )
                ],
                "has_more": True,
                "next_cursor": "cursor-2",
            },
            {
                "results": [
                    page_fixture(
                        2,
                        "次のメモ",
                        created_at_iso="2026-08-30T11:00:00+09:00",
                    )
                ],
                "has_more": False,
                "next_cursor": None,
            },
        )

        notes = reader.list_notes()

        self.assertEqual([note["id"] for note in notes], [1, 2])
        self.assertEqual(
            client.query_data_source.call_args_list,
            [
                call(
                    DATA_SOURCE_ID,
                    filter_body=None,
                    sorts=CREATED_AT_ASCENDING_SORT,
                    start_cursor=None,
                    page_size=100,
                ),
                call(
                    DATA_SOURCE_ID,
                    filter_body=None,
                    sorts=CREATED_AT_ASCENDING_SORT,
                    start_cursor="cursor-2",
                    page_size=100,
                ),
            ],
        )
        client.retrieve_data_source.assert_called_once_with(DATA_SOURCE_ID)

    def test_content_and_local_id_use_structured_filters(self):
        reader, client = reader_with_client()
        client.query_data_source.side_effect = (
            {
                "results": [page_fixture(3, "牛乳を買う")],
                "has_more": False,
            },
            {
                "results": [page_fixture(3, "牛乳を買う")],
                "has_more": False,
            },
        )

        content_results = reader.search_content("牛乳")
        local_id_results = reader.find_by_local_id(3)

        self.assertEqual(content_results[0]["content"], "牛乳を買う")
        self.assertEqual(local_id_results[0]["id"], 3)
        self.assertEqual(
            client.query_data_source.call_args_list[0].kwargs["filter_body"],
            {
                "property": CONTENT_PROPERTY,
                "rich_text": {"contains": "牛乳"},
            },
        )
        self.assertEqual(
            client.query_data_source.call_args_list[1].kwargs["filter_body"],
            {
                "property": LOCAL_ID_PROPERTY,
                "number": {"equals": 3},
            },
        )

    def test_page_id_retrieval_maps_the_major_local_fields(self):
        reader, client = reader_with_client()
        page = page_fixture(4, "Page IDで取得")
        client.retrieve_page.return_value = page

        note = reader.get_by_page_id("page-4")

        self.assertEqual(note["id"], 4)
        self.assertEqual(note["content"], "Page IDで取得")
        self.assertEqual(note["sync_key"], "sync-4")
        self.assertEqual(note["notion_page_id"], "page-4")
        self.assertEqual(note["notion_source"], "JARVIS")
        self.assertEqual(
            note["notion_last_edited_time"],
            "2026-08-30T08:00:00.000Z",
        )
        self.assertEqual(
            note["created_at"],
            datetime.fromisoformat(
                "2026-08-30T16:30:00+09:00"
            ).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        )
        client.retrieve_page.assert_called_once_with("page-4")

    def test_indexing_read_retrieves_every_content_property_page(self):
        reader, client = reader_with_client()
        client.query_data_source.return_value = {
            "results": [page_fixture(8, "queryの途中値")],
            "has_more": False,
        }
        client.retrieve_page_property_items.side_effect = (
            {
                "results": [
                    {
                        "type": "rich_text",
                        "rich_text": {"plain_text": "完全な"},
                    }
                ],
                "has_more": True,
                "next_cursor": "content-cursor-2",
            },
            {
                "results": [
                    {
                        "type": "rich_text",
                        "rich_text": {"plain_text": "Content"},
                    }
                ],
                "has_more": False,
                "next_cursor": None,
            },
        )

        notes = reader.list_notes_for_indexing()

        self.assertEqual(notes[0]["content"], "完全なContent")
        self.assertEqual(
            client.retrieve_page_property_items.call_args_list,
            [
                call(
                    "page-8",
                    "content-property-id",
                    start_cursor=None,
                    page_size=100,
                ),
                call(
                    "page-8",
                    "content-property-id",
                    start_cursor="content-cursor-2",
                    page_size=100,
                ),
            ],
        )

    def test_local_and_notion_major_fields_and_counts_match(self):
        reader, client = reader_with_client()
        local_notes = [
            {
                "id": 5,
                "content": "一致確認",
                "created_at": datetime.fromisoformat(
                    "2026-08-30T16:30:00+09:00"
                ).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                "sync_key": "sync-5",
                "notion_page_id": "page-5",
            }
        ]
        client.query_data_source.return_value = {
            "results": [page_fixture(5, "一致確認")],
            "has_more": False,
        }

        notion_notes = reader.list_notes()

        self.assertEqual(len(notion_notes), len(local_notes))

        for local, notion in zip(local_notes, notion_notes, strict=True):
            for field in (
                "id",
                "content",
                "created_at",
                "sync_key",
                "notion_page_id",
            ):
                self.assertEqual(notion[field], local[field])

    def test_invalid_pagination_cursor_fails_instead_of_losing_rows(self):
        reader, client = reader_with_client()
        client.query_data_source.return_value = {
            "results": [page_fixture(6, "未完了ページ")],
            "has_more": True,
            "next_cursor": None,
        }

        with self.assertRaisesRegex(
            NotionResponseError,
            "ページネーション",
        ):
            reader.list_notes()

    def test_duplicate_local_id_is_rejected(self):
        reader, client = reader_with_client()
        client.query_data_source.return_value = {
            "results": [
                page_fixture(7, "重複1"),
                page_fixture(7, "重複2"),
            ],
            "has_more": False,
        }

        matches = reader.find_by_local_id(7)

        self.assertEqual(len(matches), 2)

        with self.assertRaisesRegex(
            NotionResponseError,
            "複数",
        ):
            reader.get_by_local_id(7)


if __name__ == "__main__":
    unittest.main()
