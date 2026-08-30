import sys
import tempfile

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
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_BATCH_SIZE,
    OPENAI_EMBEDDING_DIMENSIONS,
    OPENAI_EMBEDDING_MODEL,
)
from app.embeddings.embedding_service import (  # noqa: E402
    EmbeddingService,
)
from app.embeddings.embedding_store import (  # noqa: E402
    EmbeddingStore,
    EmbeddingStoreError,
)
from app.integrations.notion_client import (  # noqa: E402
    NotionClient,
    NotionConfigurationError,
    NotionError,
    NotionResponseError,
)
from app.integrations.openai_embedding_client import (  # noqa: E402
    EmbeddingError,
    OpenAIEmbeddingClient,
)
from app.vector.chroma_index import (  # noqa: E402
    ChromaIndex,
    ChromaIndexError,
)
from app.vector.notion_chroma_sync import (  # noqa: E402
    ChromaNotionPageAuditor,
    NotionChromaSyncService,
)


TEST_PAGE_TITLE_PREFIX = "JARVIS Chroma Verification"


@dataclass(frozen=True)
class ChromaVerificationResult:
    page_id: str
    collection_name: str
    chunk_count: int
    first_embedded: int
    second_skipped: int
    missing_reason: str


def verify_chroma(
    *,
    notion_client: NotionClient,
    parent_page_id: str,
    now: datetime | None = None,
) -> ChromaVerificationResult:
    normalized_parent_id = (parent_page_id or "").strip()

    if not normalized_parent_id:
        raise NotionConfigurationError(
            "NOTION_PARENT_PAGE_ID が設定されていません。"
        )

    timestamp = (now or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    created_page_id = None
    moved_to_trash = False

    try:
        created = notion_client.create_child_page(
            parent_page_id=normalized_parent_id,
            title=f"{TEST_PAGE_TITLE_PREFIX} - {timestamp}",
            children=_verification_blocks(),
        )
        created_page_id = _require_text(created, "id")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            open_indexes = []
            embedding_store = EmbeddingStore(
                root / "embeddings.sqlite3"
            )
            embedding_service = EmbeddingService(
                client=OpenAIEmbeddingClient(api_key=OPENAI_API_KEY),
                store=embedding_store,
                model=OPENAI_EMBEDDING_MODEL,
                dimensions=OPENAI_EMBEDDING_DIMENSIONS,
                batch_size=OPENAI_EMBEDDING_BATCH_SIZE,
            )
            chroma_path = root / "chroma"
            chroma_index = ChromaIndex(
                model=OPENAI_EMBEDDING_MODEL,
                dimensions=OPENAI_EMBEDDING_DIMENSIONS,
                persistence_path=chroma_path,
            )
            open_indexes.append(chroma_index)

            try:
                sync_service = NotionChromaSyncService(
                    chunking_service=NotionPageChunkingService(
                        client=notion_client
                    ),
                    embedding_service=embedding_service,
                    embedding_store=embedding_store,
                    chroma_index=chroma_index,
                    model=OPENAI_EMBEDDING_MODEL,
                    dimensions=OPENAI_EMBEDDING_DIMENSIONS,
                )
                first = sync_service.sync_page(created_page_id)
                second = sync_service.sync_page(created_page_id)
                reopened = ChromaIndex(
                    model=OPENAI_EMBEDDING_MODEL,
                    dimensions=OPENAI_EMBEDDING_DIMENSIONS,
                    persistence_path=chroma_path,
                )
                open_indexes.append(reopened)

                if (
                    first.chunk_count < 1
                    or first.embedding_result.embedded_chunks < 1
                    or second.embedding_result.embedded_chunks != 0
                    or second.embedding_result.skipped_unchanged
                    != first.chunk_count
                    or reopened.get_page_chunk_ids(created_page_id)
                    != chroma_index.get_page_chunk_ids(created_page_id)
                ):
                    raise ChromaIndexError(
                        "Chromaの永続化または未変更Chunkスキップ結果が不正です。"
                    )

                records = reopened.get_page_records(created_page_id)
                metadatas = records.get("metadatas")

                if (
                    not isinstance(metadatas, list)
                    or not metadatas
                    or any(
                        not isinstance(metadata, dict)
                        or metadata.get("notion_page_id") != created_page_id
                        or not metadata.get("title")
                        or not metadata.get("notion_url")
                        for metadata in metadatas
                    )
                ):
                    raise ChromaIndexError(
                        "ChromaのNotion Metadataが不正です。"
                    )

                other_collection = ChromaIndex(
                    model=(
                        f"{OPENAI_EMBEDDING_MODEL}-verification-other"
                    ),
                    dimensions=OPENAI_EMBEDDING_DIMENSIONS,
                    persistence_path=chroma_path,
                )
                open_indexes.append(other_collection)

                if (
                    other_collection.collection_name
                    == chroma_index.collection_name
                    or other_collection.count() != 0
                ):
                    raise ChromaIndexError(
                        "Embedding model別Collection分離に失敗しました。"
                    )

                notion_client.update_page(created_page_id, in_trash=True)
                moved_to_trash = True
                missing = ChromaNotionPageAuditor(
                    notion_client=notion_client,
                    chroma_index=reopened,
                ).find_missing_pages()

                if (
                    len(missing) != 1
                    or missing[0].notion_page_id != created_page_id
                ):
                    raise ChromaIndexError(
                        "Notionに存在しないPageの検出に失敗しました。"
                    )

                result = ChromaVerificationResult(
                    page_id=created_page_id,
                    collection_name=chroma_index.collection_name,
                    chunk_count=first.chunk_count,
                    first_embedded=first.embedding_result.embedded_chunks,
                    second_skipped=(
                        second.embedding_result.skipped_unchanged
                    ),
                    missing_reason=missing[0].reason,
                )
            finally:
                for index in reversed(open_indexes):
                    index.close()

            return result
    finally:
        if created_page_id is not None and not moved_to_trash:
            notion_client.update_page(created_page_id, in_trash=True)


def main() -> int:
    try:
        result = verify_chroma(
            notion_client=NotionClient(
                api_token=NOTION_API_TOKEN,
                api_version=NOTION_API_VERSION,
            ),
            parent_page_id=NOTION_PARENT_PAGE_ID or "",
        )
    except (
        NotionError,
        EmbeddingError,
        EmbeddingStoreError,
        ChromaIndexError,
    ) as error:
        print(f"Chroma確認に失敗しました: {error}", file=sys.stderr)
        return 1

    print("Chroma確認に成功しました。")
    print(f"Page ID (in trash): {result.page_id}")
    print(f"Collection: {result.collection_name}")
    print(f"Chunks: {result.chunk_count}")
    print(f"First embedded: {result.first_embedded}")
    print(f"Second skipped: {result.second_skipped}")
    print(f"Missing Page detection: {result.missing_reason}")
    print("ChromaとEmbeddingの検証データは一時領域から削除済みです。")
    return 0


def _verification_blocks() -> list[dict]:
    return [
        {
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [_text("Phase 7 Chroma verification")],
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    _text(
                        "This content must originate in Notion and remain "
                        "rebuildable."
                    )
                ],
            },
        },
    ]


def _text(content: str) -> dict:
    return {"type": "text", "text": {"content": content}}


def _require_text(payload: dict, key: str) -> str:
    value = payload.get(key)

    if not isinstance(value, str) or not value.strip():
        raise NotionResponseError(
            f"Chromaテストページの{key}を取得できませんでした。"
        )

    return value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
