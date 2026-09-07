import argparse
import sys

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.chunking.notion_chunker import (  # noqa: E402
    NotionPageChunkingService,
)
from app.chunking.notion_memo_chunker import NotionMemoChunker  # noqa: E402
from app.config import (  # noqa: E402
    CHROMA_PERSIST_DIRECTORY,
    EMBEDDINGS_DB_FILE,
    NOTION_API_TOKEN,
    NOTION_API_VERSION,
    NOTION_KNOWLEDGE_SYNC_RETRY_COUNT,
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
from app.integrations.notion_memo_reader import NotionMemoReader  # noqa: E402
from app.integrations.notion_resources import (  # noqa: E402
    resolve_notes_data_source_id,
)
from app.integrations.openai_embedding_client import (  # noqa: E402
    EmbeddingError,
    OpenAIEmbeddingClient,
)
from app.knowledge_sync.lock import (  # noqa: E402
    KnowledgeSyncAlreadyRunningError,
    KnowledgeSyncLock,
)
from app.knowledge_sync.registry import (  # noqa: E402
    KnowledgeSourceRegistryError,
    KnowledgeSourceRegistryStore,
)
from app.knowledge_sync.service import (  # noqa: E402
    KnowledgeSyncSummary,
    NotionKnowledgeSyncService,
)
from app.knowledge_sync.state import (  # noqa: E402
    KnowledgeSyncStateError,
    KnowledgeSyncStateStore,
)
from app.vector.chroma_index import ChromaIndex, ChromaIndexError  # noqa: E402
from app.vector.notion_chroma_sync import (  # noqa: E402
    NotionChromaSyncService,
)


def sync_notion_knowledge(*, dry_run: bool) -> KnowledgeSyncSummary:
    registry = KnowledgeSourceRegistryStore().load()
    notion_client = NotionClient(
        api_token=NOTION_API_TOKEN,
        api_version=NOTION_API_VERSION,
    )
    page_chunking_service = NotionPageChunkingService(client=notion_client)
    notes_data_source_id = resolve_notes_data_source_id()
    memo_reader = (
        NotionMemoReader(
            client=notion_client,
            data_source_id=notes_data_source_id,
        )
        if notes_data_source_id is not None
        else None
    )
    chroma_index = ChromaIndex(
        model=OPENAI_EMBEDDING_MODEL,
        dimensions=OPENAI_EMBEDDING_DIMENSIONS,
        persistence_path=CHROMA_PERSIST_DIRECTORY,
        create_if_missing=not dry_run,
    )

    try:
        chroma_sync_service = None

        if not dry_run:
            embedding_store = EmbeddingStore(EMBEDDINGS_DB_FILE)
            embedding_service = EmbeddingService(
                client=OpenAIEmbeddingClient(api_key=OPENAI_API_KEY),
                store=embedding_store,
                model=OPENAI_EMBEDDING_MODEL,
                dimensions=OPENAI_EMBEDDING_DIMENSIONS,
                batch_size=OPENAI_EMBEDDING_BATCH_SIZE,
            )
            chroma_sync_service = NotionChromaSyncService(
                chunking_service=page_chunking_service,
                embedding_service=embedding_service,
                embedding_store=embedding_store,
                chroma_index=chroma_index,
                model=OPENAI_EMBEDDING_MODEL,
                dimensions=OPENAI_EMBEDDING_DIMENSIONS,
            )

        return NotionKnowledgeSyncService(
            registry=registry,
            page_chunking_service=page_chunking_service,
            memo_chunker=NotionMemoChunker(),
            memo_reader=memo_reader,
            chroma_index=chroma_index,
            state_store=KnowledgeSyncStateStore(),
            embedding_model=OPENAI_EMBEDDING_MODEL,
            embedding_dimensions=OPENAI_EMBEDDING_DIMENSIONS,
            chroma_sync_service=chroma_sync_service,
            retry_count=NOTION_KNOWLEDGE_SYNC_RETRY_COUNT,
        ).run(dry_run=dry_run)
    finally:
        chroma_index.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "登録済みNotion PageとNotesを差分判定してChromaへ同期します。"
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    dry_run = not arguments.apply

    try:
        with KnowledgeSyncLock():
            summary = sync_notion_knowledge(dry_run=dry_run)
    except (
        NotionError,
        EmbeddingError,
        EmbeddingStoreError,
        ChromaIndexError,
        KnowledgeSourceRegistryError,
        KnowledgeSyncStateError,
        KnowledgeSyncAlreadyRunningError,
        ValueError,
    ) as error:
        print(f"Notion知識同期に失敗しました: {error}", file=sys.stderr)
        return 1

    _print_summary(summary)
    return 1 if summary.failures else 0


def _print_summary(summary: KnowledgeSyncSummary) -> None:
    print("DRY RUN" if summary.dry_run else "APPLY")
    print(f"Collection: {summary.collection_name}")
    print(f"Changed pages: {summary.changed_pages}")
    print(f"Unchanged pages: {summary.unchanged_pages}")
    print(f"Removed pages: {summary.removed_pages}")
    print(f"Failures: {len(summary.failures)}")

    for action in summary.actions:
        print(
            f"- {action.status}: {action.source_type} / "
            f"{action.notion_page_id} / {action.reason} / "
            f"chunks={action.chunk_count} / "
            f"embedded={action.embedded_chunks} / "
            f"deleted={action.deleted_chunks}"
        )

    if summary.dry_run:
        print("変更は行っていません。--applyで同期します。")


if __name__ == "__main__":
    raise SystemExit(main())

