import unittest

from app.chunking.notion_memo_chunker import (
    NOTION_MEMO_SOURCE_TYPE,
    NotionMemoChunker,
)
from app.integrations.notion_client import NotionResponseError


PAGE_ID = "11111111-2222-3333-4444-555555555555"


def memo_fixture(content: str, **overrides):
    memo = {
        "id": 42,
        "content": content,
        "notion_page_id": PAGE_ID,
        "notion_title": "AECの設計メモ",
        "notion_url": "https://www.notion.so/aec-memo",
        "notion_last_edited_time": "2026-09-03T01:02:03.000Z",
    }
    memo.update(overrides)
    return memo


class NotionMemoChunkerTests(unittest.TestCase):
    def test_chunks_content_property_with_title_and_metadata(self):
        chunks = NotionMemoChunker().chunk(
            memo_fixture("AECは段階的に評価する。")
        )

        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertEqual(
            chunk.content,
            "# AECの設計メモ\n\nAECは段階的に評価する。",
        )
        self.assertEqual(chunk.title, "AECの設計メモ")
        self.assertEqual(chunk.notion_page_id, PAGE_ID)
        self.assertEqual(chunk.source_type, NOTION_MEMO_SOURCE_TYPE)
        self.assertEqual(chunk.heading_path, ("AECの設計メモ",))
        self.assertEqual(chunk.notion_url, "https://www.notion.so/aec-memo")
        self.assertTrue(chunk.block_id.startswith("notion-property:"))

    def test_same_content_produces_stable_chunk_ids(self):
        chunker = NotionMemoChunker()
        first = chunker.chunk(memo_fixture("同じ内容"))
        second = chunker.chunk(memo_fixture("同じ内容"))
        changed = chunker.chunk(memo_fixture("変更した内容"))

        self.assertEqual(
            [chunk.chunk_id for chunk in first],
            [chunk.chunk_id for chunk in second],
        )
        self.assertNotEqual(first[0].chunk_id, changed[0].chunk_id)

    def test_splits_long_content_and_keeps_heading(self):
        chunks = NotionMemoChunker(max_chunk_characters=160).chunk(
            memo_fixture(" ".join(["開発項目"] * 80))
        )

        self.assertGreater(len(chunks), 1)
        self.assertEqual(
            [chunk.chunk_index for chunk in chunks],
            list(range(len(chunks))),
        )
        self.assertTrue(
            all(
                chunk.content.startswith("# AECの設計メモ\n\n")
                for chunk in chunks
            )
        )
        self.assertTrue(all(len(chunk.content) <= 160 for chunk in chunks))

    def test_empty_content_is_excluded(self):
        self.assertEqual(NotionMemoChunker().chunk(memo_fixture("  \n")), [])

    def test_missing_page_metadata_is_rejected_without_content_in_error(self):
        with self.assertRaisesRegex(NotionResponseError, "notion_url") as raised:
            NotionMemoChunker().chunk(
                memo_fixture("secret memo content", notion_url="")
            )

        self.assertNotIn("secret memo content", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
