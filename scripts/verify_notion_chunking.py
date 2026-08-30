import sys

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.chunking.notion_chunker import (  # noqa: E402
    NotionPageChunkingService,
)
from app.config import (  # noqa: E402
    NOTION_API_TOKEN,
    NOTION_API_VERSION,
    NOTION_PARENT_PAGE_ID,
)
from app.integrations.notion_client import (  # noqa: E402
    NotionClient,
    NotionConfigurationError,
    NotionError,
    NotionResponseError,
)


TEST_PAGE_TITLE_PREFIX = "JARVIS Notion Chunking Test"
REQUIRED_METADATA_FIELDS = {
    "chunk_id",
    "notion_page_id",
    "block_id",
    "title",
    "chunk_index",
    "content_hash",
    "last_edited_time",
    "source_type",
    "notion_url",
}


@dataclass(frozen=True)
class NotionChunkingVerificationResult:
    page_id: str
    chunk_count: int
    block_count: int
    chunk_ids: tuple[str, ...]


def verify_notion_chunking(
    client: NotionClient,
    *,
    parent_page_id: str,
    now: datetime | None = None,
) -> NotionChunkingVerificationResult:
    normalized_parent_id = (parent_page_id or "").strip()

    if not normalized_parent_id:
        raise NotionConfigurationError(
            "NOTION_PARENT_PAGE_ID が設定されていません。"
        )

    timestamp = (now or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    title = f"{TEST_PAGE_TITLE_PREFIX} - {timestamp}"
    created_page_id = None

    try:
        created_page = client.create_child_page(
            parent_page_id=normalized_parent_id,
            title=title,
            children=_verification_blocks(),
        )
        created_page_id = _require_text(
            created_page,
            "id",
            "ChunkingテストページのPage IDを取得できませんでした。",
        )
        service = NotionPageChunkingService(
            client=client,
            max_chunk_characters=180,
        )
        first = service.chunk_page(created_page_id)
        second = service.chunk_page(created_page_id)

        if not first:
            raise NotionResponseError(
                "ChunkingテストページからChunkを生成できませんでした。"
            )

        first_fingerprints = [
            (chunk.chunk_id, chunk.content_hash, chunk.content)
            for chunk in first
        ]
        second_fingerprints = [
            (chunk.chunk_id, chunk.content_hash, chunk.content)
            for chunk in second
        ]

        if first_fingerprints != second_fingerprints:
            raise NotionResponseError(
                "同じNotionページの再同期でChunk IDが一致しませんでした。"
            )

        combined_content = "\n".join(chunk.content for chunk in first)

        for expected in (
            "# Phase 5 verification",
            "Recursive block retrieval",
            "Nested child content",
            "Code (python):",
            "print('chunking')",
        ):
            if expected not in combined_content:
                raise NotionResponseError(
                    f"正規化後のChunkに必要な本文がありません: {expected}"
                )

        for expected_index, chunk in enumerate(first):
            metadata = chunk.to_dict()
            missing = REQUIRED_METADATA_FIELDS.difference(metadata)

            if missing:
                raise NotionResponseError(
                    "Chunk Metadataが不足しています: "
                    f"{', '.join(sorted(missing))}"
                )

            if chunk.chunk_index != expected_index:
                raise NotionResponseError(
                    "Chunk Indexが文書順になっていません。"
                )

            if not chunk.chunk_id.startswith("notion-chunk:"):
                raise NotionResponseError(
                    "Chunk IDの形式が不正です。"
                )

            if _canonical_id(chunk.notion_page_id) != _canonical_id(
                created_page_id
            ):
                raise NotionResponseError(
                    "ChunkのNotion Page IDが一致しません。"
                )

        unique_block_ids = {
            block_id
            for chunk in first
            for block_id in chunk.block_ids
        }
        return NotionChunkingVerificationResult(
            page_id=created_page_id,
            chunk_count=len(first),
            block_count=len(unique_block_ids),
            chunk_ids=tuple(chunk.chunk_id for chunk in first),
        )
    finally:
        if created_page_id is not None:
            client.update_page(created_page_id, in_trash=True)


def main() -> int:
    try:
        client = NotionClient(
            api_token=NOTION_API_TOKEN,
            api_version=NOTION_API_VERSION,
        )
        result = verify_notion_chunking(
            client,
            parent_page_id=NOTION_PARENT_PAGE_ID or "",
        )
    except NotionError as error:
        print(f"Notion Chunking確認に失敗しました: {error}", file=sys.stderr)
        return 1

    print("Notion Chunking確認に成功しました。")
    print(f"Page ID (in trash): {result.page_id}")
    print(f"Source Block count: {result.block_count}")
    print(f"Chunk count: {result.chunk_count}")

    for chunk_id in result.chunk_ids:
        print(f"Chunk ID: {chunk_id}")

    return 0


def _verification_blocks() -> list[dict]:
    return [
        {
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [_text("Phase 5 verification")],
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [_text("Recursive block retrieval")],
            },
        },
        {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [_text("Nested section")],
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [_text("Nested child content")],
                        },
                    }
                ],
            },
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [_text("Code sample")],
            },
        },
        {
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": [_text("print('chunking')\nprint('stable')")],
                "language": "python",
            },
        },
    ]


def _text(content: str) -> dict:
    return {
        "type": "text",
        "text": {"content": content},
    }


def _require_text(payload: dict, key: str, message: str) -> str:
    value = payload.get(key)

    if not isinstance(value, str) or not value.strip():
        raise NotionResponseError(message)

    return value.strip()


def _canonical_id(value: str) -> str:
    return value.strip().replace("-", "").lower()


if __name__ == "__main__":
    raise SystemExit(main())
