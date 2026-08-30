import unittest

from unittest.mock import Mock, call

from app.chunking.notion_blocks import (
    NormalizedNotionBlock,
    NotionBlockNormalizer,
    NotionBlockNode,
    NotionBlockTreeFetcher,
)
from app.chunking.notion_chunker import (
    NotionPageChunker,
    NotionPageChunkingService,
)
from app.integrations.notion_client import (
    NotionClient,
    NotionResponseError,
)


PAGE_ID = "11111111-2222-3333-4444-555555555555"
PAGE_URL = "https://www.notion.so/Chunking-Test-11111111222233334444555555555555"


def _rich_text(value):
    return [
        {
            "type": "text",
            "plain_text": value,
            "text": {"content": value},
        }
    ]


def _block(
    block_id,
    block_type,
    text=None,
    *,
    has_children=False,
    payload=None,
):
    if payload is None:
        payload = {"rich_text": _rich_text(text or "")}

    return {
        "object": "block",
        "id": block_id,
        "type": block_type,
        "has_children": has_children,
        "last_edited_time": "2026-08-30T10:00:00.000Z",
        block_type: payload,
    }


def _node(block, *, parent_id=PAGE_ID, depth=0, children=()):
    return NotionBlockNode(
        block=block,
        parent_id=parent_id,
        depth=depth,
        children=children,
    )


def _normalized(
    block_id,
    text,
    *,
    block_type="paragraph",
    heading_level=None,
    depth=0,
):
    return NormalizedNotionBlock(
        block_id=block_id,
        block_type=block_type,
        text=text,
        depth=depth,
        parent_id=PAGE_ID,
        heading_level=heading_level,
        last_edited_time="2026-08-30T10:00:00.000Z",
    )


def _page(*, last_edited_time="2026-08-30T10:00:00.000Z"):
    return {
        "object": "page",
        "id": PAGE_ID,
        "last_edited_time": last_edited_time,
        "url": PAGE_URL,
        "properties": {
            "Name": {
                "type": "title",
                "title": _rich_text("Chunking Test"),
            }
        },
    }


class NotionBlockTreeFetcherTests(unittest.TestCase):
    def test_fetches_every_page_then_recursively_fetches_children(self):
        heading = _block("heading-id", "heading_1", "Overview")
        toggle = _block(
            "toggle-id",
            "toggle",
            "Details",
            has_children=True,
        )
        code = _block(
            "code-id",
            "code",
            payload={
                "rich_text": _rich_text("print('ok')"),
                "language": "python",
            },
        )
        nested = _block("nested-id", "paragraph", "Nested text")
        client = Mock(spec=NotionClient)
        client.retrieve_block_children.side_effect = (
            {
                "results": [heading, toggle],
                "has_more": True,
                "next_cursor": "root-next",
            },
            {
                "results": [code],
                "has_more": False,
                "next_cursor": None,
            },
            {
                "results": [nested],
                "has_more": False,
                "next_cursor": None,
            },
        )

        nodes = NotionBlockTreeFetcher(client=client).fetch_page_blocks(
            PAGE_ID
        )

        self.assertEqual(
            [node.block_id for node in nodes],
            ["heading-id", "toggle-id", "code-id"],
        )
        self.assertEqual(nodes[1].children[0].block_id, "nested-id")
        self.assertEqual(nodes[1].children[0].depth, 1)
        self.assertEqual(
            client.retrieve_block_children.call_args_list,
            [
                call(PAGE_ID, start_cursor=None, page_size=100),
                call(PAGE_ID, start_cursor="root-next", page_size=100),
                call("toggle-id", start_cursor=None, page_size=100),
            ],
        )

    def test_rejects_missing_or_repeated_pagination_cursor(self):
        for next_cursor in (None, "same-cursor"):
            with self.subTest(next_cursor=next_cursor):
                client = Mock(spec=NotionClient)

                if next_cursor is None:
                    client.retrieve_block_children.return_value = {
                        "results": [],
                        "has_more": True,
                        "next_cursor": None,
                    }
                else:
                    client.retrieve_block_children.side_effect = (
                        {
                            "results": [],
                            "has_more": True,
                            "next_cursor": next_cursor,
                        },
                        {
                            "results": [],
                            "has_more": True,
                            "next_cursor": next_cursor,
                        },
                    )

                with self.assertRaises(NotionResponseError):
                    NotionBlockTreeFetcher(
                        client=client
                    ).fetch_page_blocks(PAGE_ID)


class NotionBlockNormalizerTests(unittest.TestCase):
    def test_normalizes_supported_blocks_in_document_order(self):
        nested = _node(
            _block("nested-id", "paragraph", "Nested text"),
            parent_id="toggle-id",
            depth=1,
        )
        nodes = (
            _node(_block("heading-id", "heading_1", "Overview")),
            _node(
                _block(
                    "empty-id",
                    "paragraph",
                    payload={
                        "rich_text": [
                            {
                                "type": "text",
                                "plain_text": "   ",
                                "annotations": {"bold": True},
                            }
                        ]
                    },
                )
            ),
            _node(_block("list-id", "bulleted_list_item", "First")),
            _node(
                _block(
                    "code-id",
                    "code",
                    payload={
                        "rich_text": _rich_text("line 1\nline 2"),
                        "language": "python",
                    },
                )
            ),
            _node(
                _block(
                    "toggle-id",
                    "toggle",
                    "Details",
                    has_children=True,
                ),
                children=(nested,),
            ),
            _node(
                _block(
                    "divider-id",
                    "divider",
                    payload={},
                )
            ),
        )

        blocks = NotionBlockNormalizer().normalize(nodes)

        self.assertEqual(
            [(block.block_type, block.text) for block in blocks],
            [
                ("heading_1", "Overview"),
                ("bulleted_list_item", "- First"),
                ("code", "Code (python):\nline 1\nline 2"),
                ("toggle", "Details"),
                ("paragraph", "Nested text"),
            ],
        )
        self.assertEqual(blocks[0].heading_level, 1)
        self.assertEqual(blocks[-1].depth, 1)

    def test_uses_plain_text_independent_of_annotations(self):
        base = _block("paragraph-id", "paragraph", "same text")
        decorated = _block(
            "paragraph-id",
            "paragraph",
            payload={
                "rich_text": [
                    {
                        "plain_text": "same text",
                        "annotations": {
                            "bold": True,
                            "italic": True,
                            "color": "red",
                        },
                    }
                ]
            },
        )

        normalizer = NotionBlockNormalizer()
        self.assertEqual(
            normalizer.normalize((_node(base),))[0].text,
            normalizer.normalize((_node(decorated),))[0].text,
        )


class NotionPageChunkerTests(unittest.TestCase):
    def test_preserves_heading_paths_splits_content_and_adds_metadata(self):
        blocks = [
            _normalized(
                "heading-1",
                "Project",
                block_type="heading_1",
                heading_level=1,
            ),
            _normalized("paragraph-1", "A" * 80),
            _normalized(
                "heading-2",
                "Details",
                block_type="heading_2",
                heading_level=2,
            ),
            _normalized("paragraph-2", "B" * 180),
        ]

        chunks = NotionPageChunker(
            max_chunk_characters=100
        ).chunk(page=_page(), blocks=blocks)

        self.assertGreaterEqual(len(chunks), 3)
        self.assertTrue(chunks[0].content.startswith("# Project\n\n"))
        self.assertTrue(
            any(
                chunk.content.startswith("# Project\n## Details\n\n")
                for chunk in chunks
            )
        )
        self.assertTrue(
            all(len(chunk.content) <= 100 for chunk in chunks)
        )
        self.assertEqual(
            [chunk.chunk_index for chunk in chunks],
            list(range(len(chunks))),
        )

        first = chunks[0].to_dict()
        self.assertEqual(first["notion_page_id"], PAGE_ID)
        self.assertEqual(first["title"], "Chunking Test")
        self.assertEqual(first["source_type"], "notion_page")
        self.assertEqual(first["notion_url"], PAGE_URL)
        self.assertEqual(
            set(
                (
                    "chunk_id",
                    "notion_page_id",
                    "block_id",
                    "title",
                    "chunk_index",
                    "content_hash",
                    "last_edited_time",
                    "source_type",
                    "notion_url",
                )
            ).difference(first),
            set(),
        )

    def test_same_content_resync_produces_same_chunk_ids(self):
        blocks = [
            _normalized(
                "heading-id",
                "Overview",
                block_type="heading_1",
                heading_level=1,
            ),
            _normalized("paragraph-id", "Stable content"),
        ]
        chunker = NotionPageChunker()

        first = chunker.chunk(page=_page(), blocks=blocks)
        second = chunker.chunk(
            page=_page(last_edited_time="2026-08-31T12:00:00.000Z"),
            blocks=blocks,
        )

        self.assertEqual(
            [chunk.chunk_id for chunk in first],
            [chunk.chunk_id for chunk in second],
        )
        self.assertEqual(
            [chunk.content_hash for chunk in first],
            [chunk.content_hash for chunk in second],
        )
        self.assertNotEqual(
            first[0].last_edited_time,
            second[0].last_edited_time,
        )

    def test_content_change_produces_a_different_chunk_id(self):
        chunker = NotionPageChunker()
        first = chunker.chunk(
            page=_page(),
            blocks=[_normalized("paragraph-id", "Before")],
        )
        second = chunker.chunk(
            page=_page(),
            blocks=[_normalized("paragraph-id", "After")],
        )

        self.assertNotEqual(first[0].chunk_id, second[0].chunk_id)

    def test_consecutive_headings_are_not_dropped(self):
        blocks = [
            _normalized(
                "heading-1",
                "Parent",
                block_type="heading_1",
                heading_level=1,
            ),
            _normalized(
                "heading-2",
                "Child",
                block_type="heading_2",
                heading_level=2,
            ),
            _normalized("paragraph-id", "Body"),
        ]

        chunks = NotionPageChunker().chunk(
            page=_page(),
            blocks=blocks,
        )

        self.assertEqual(
            [chunk.content for chunk in chunks],
            ["# Parent", "# Parent\n## Child\n\nBody"],
        )
        self.assertEqual(chunks[0].block_id, "heading-1")
        self.assertEqual(chunks[1].block_id, "heading-2")


class NotionPageChunkingServiceTests(unittest.TestCase):
    def test_retrieves_page_blocks_normalizes_and_chunks(self):
        client = Mock(spec=NotionClient)
        client.retrieve_page.return_value = _page()
        client.retrieve_block_children.return_value = {
            "results": [_block("paragraph-id", "paragraph", "Content")],
            "has_more": False,
            "next_cursor": None,
        }

        chunks = NotionPageChunkingService(client=client).chunk_page(
            PAGE_ID
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, "Content")
        client.retrieve_page.assert_called_once_with(PAGE_ID)
        client.retrieve_block_children.assert_called_once_with(
            PAGE_ID,
            start_cursor=None,
            page_size=100,
        )


if __name__ == "__main__":
    unittest.main()
