import argparse
import sys

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.chunking.notion_chunker import (  # noqa: E402
    NotionPageChunkingService,
)
from app.chunking.notion_memo_chunker import (  # noqa: E402
    NotionMemoChunker,
)
from app.config import (  # noqa: E402
    CHROMA_PERSIST_DIRECTORY,
    EMBEDDINGS_DB_FILE,
    NOTION_API_TOKEN,
    NOTION_API_VERSION,
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_BATCH_SIZE,
    OPENAI_EMBEDDING_DIMENSIONS,
    OPENAI_EMBEDDING_MODEL,
)
from app.embeddings.embedding_service import EmbeddingService  # noqa: E402
from app.embeddings.embedding_store import (  # noqa: E402
    EmbeddingStore,
    EmbeddingStoreError,
)
from app.integrations.notion_client import (  # noqa: E402
    NotionClient,
    NotionConfigurationError,
    NotionError,
)
from app.integrations.notion_memo_reader import (  # noqa: E402
    NotionMemoReader,
)
from app.integrations.notion_resources import (  # noqa: E402
    resolve_notes_data_source_id,
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
    NotionChromaSyncService,
)
from app.vector.notion_memo_chroma_sync import (  # noqa: E402
    NotionMemoChromaSyncService,
    NotionMemoChromaSyncSummary,
)


def sync_notion_notes_to_chroma(
    *,
    dry_run: bool,
) -> NotionMemoChromaSyncSummary:
    data_source_id = resolve_notes_data_source_id()

    if data_source_id is None:
        raise NotionConfigurationError(
            "Notes用Data Source IDが設定されていません。"
        )

    notion_client = NotionClient(
        api_token=NOTION_API_TOKEN,
        api_version=NOTION_API_VERSION,
    )
    reader = NotionMemoReader(
        client=notion_client,
        data_source_id=data_source_id,
    )
    chunker = NotionMemoChunker()

    if dry_run:
        return NotionMemoChromaSyncService(
            reader=reader,
            chunker=chunker,
        ).sync_all(dry_run=True)

    embedding_store = EmbeddingStore(EMBEDDINGS_DB_FILE)
    embedding_service = EmbeddingService(
        client=OpenAIEmbeddingClient(api_key=OPENAI_API_KEY),
        store=embedding_store,
        model=OPENAI_EMBEDDING_MODEL,
        dimensions=OPENAI_EMBEDDING_DIMENSIONS,
        batch_size=OPENAI_EMBEDDING_BATCH_SIZE,
    )
    chroma_index = ChromaIndex(
        model=OPENAI_EMBEDDING_MODEL,
        dimensions=OPENAI_EMBEDDING_DIMENSIONS,
        persistence_path=CHROMA_PERSIST_DIRECTORY,
    )

    try:
        chroma_sync_service = NotionChromaSyncService(
            chunking_service=NotionPageChunkingService(
                client=notion_client
            ),
            embedding_service=embedding_service,
            embedding_store=embedding_store,
            chroma_index=chroma_index,
            model=OPENAI_EMBEDDING_MODEL,
            dimensions=OPENAI_EMBEDDING_DIMENSIONS,
        )
        return NotionMemoChromaSyncService(
            reader=reader,
            chunker=chunker,
            chroma_sync_service=chroma_sync_service,
        ).sync_all(dry_run=False)
    finally:
        chroma_index.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Notes Data SourceのContentをChunk化しChromaへ一括同期します。"
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Notionを読み取り、Chunk候補だけを確認します（既定）。",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Embedding作成とChroma同期を実行します。",
    )
    arguments = parser.parse_args()
    dry_run = not arguments.apply

    try:
        result = sync_notion_notes_to_chroma(dry_run=dry_run)
    except (
        NotionError,
        EmbeddingError,
        EmbeddingStoreError,
        ChromaIndexError,
        ValueError,
    ) as error:
        print(f"Notion Memo一括同期に失敗しました: {error}", file=sys.stderr)
        return 1

    print("DRY RUN" if result.dry_run else "APPLY")
    print(f"Notes pages: {result.total_pages}")
    print(f"Pages with Content: {result.pages_with_content}")
    print(f"Empty Content pages: {result.empty_pages}")
    print(f"Candidate chunks: {result.candidate_chunks}")
    print(f"Synced pages: {result.synced_pages}")
    print(f"Embedded now: {result.embedded_chunks}")
    print(f"Embedding skipped: {result.skipped_unchanged}")
    print(f"Stale chunks deleted: {result.deleted_chunks}")
    print(f"Failures: {len(result.failures)}")

    for failure in result.failures:
        print(
            f"- Local ID={failure.local_id}, "
            f"Page ID={failure.notion_page_id}, "
            f"{failure.error_type}: {failure.message}",
            file=sys.stderr,
        )

    if result.dry_run:
        print("変更は行っていません。実行する場合は--applyを指定してください。")

    return 1 if result.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
