import hashlib

from typing import Any

from app.chunking.notion_blocks import NormalizedNotionBlock
from app.chunking.notion_chunker import (
    DEFAULT_MAX_CHUNK_CHARACTERS,
    NotionChunk,
    NotionPageChunker,
)
from app.integrations.notion_client import NotionResponseError


NOTION_MEMO_SOURCE_TYPE = "notion_memo"


class NotionMemoChunker:
    def __init__(
        self,
        *,
        max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
    ):
        self._page_chunker = NotionPageChunker(
            max_chunk_characters=max_chunk_characters
        )

    def chunk(self, memo: dict[str, Any]) -> list[NotionChunk]:
        if not isinstance(memo, dict):
            raise NotionResponseError("Chunk化するNotion Memoが不正です。")

        content = memo.get("content")

        if not isinstance(content, str):
            raise NotionResponseError(
                "Notion MemoのContentを取得できませんでした。"
            )

        if not content.strip():
            return []

        page_id = _required_memo_text(memo, "notion_page_id")
        title = _memo_title(memo)
        last_edited_time = _required_memo_text(
            memo,
            "notion_last_edited_time",
        )
        notion_url = _required_memo_text(memo, "notion_url")
        title_block_id = _property_block_id(page_id, "title")
        content_block_id = _property_block_id(page_id, "content")
        blocks = [
            NormalizedNotionBlock(
                block_id=title_block_id,
                block_type="heading_1",
                text=title,
                depth=0,
                parent_id=page_id,
                heading_level=1,
                last_edited_time=last_edited_time,
            ),
            NormalizedNotionBlock(
                block_id=content_block_id,
                block_type="paragraph",
                text=content.strip(),
                depth=0,
                parent_id=page_id,
                heading_level=None,
                last_edited_time=last_edited_time,
            ),
        ]
        page = {
            "id": page_id,
            "last_edited_time": last_edited_time,
            "url": notion_url,
            "properties": {
                "Title": {
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": title},
                            "plain_text": title,
                        }
                    ]
                }
            },
        }
        return self._page_chunker.chunk(
            page=page,
            blocks=blocks,
            source_type=NOTION_MEMO_SOURCE_TYPE,
        )


def _memo_title(memo: dict[str, Any]) -> str:
    value = memo.get("notion_title")

    if isinstance(value, str):
        normalized = " ".join(value.split())

        if normalized:
            return normalized

    note_id = memo.get("id")

    if isinstance(note_id, int) and not isinstance(note_id, bool):
        return f"Memo {note_id}"

    return "Untitled Memo"


def _required_memo_text(memo: dict[str, Any], key: str) -> str:
    value = memo.get(key)

    if not isinstance(value, str) or not value.strip():
        raise NotionResponseError(
            f"Notion Memoの{key}を取得できませんでした。"
        )

    return value.strip()


def _property_block_id(page_id: str, property_name: str) -> str:
    canonical_page_id = page_id.strip().replace("-", "").lower()
    identity = f"{canonical_page_id}\0{property_name}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"notion-property:{digest}"
