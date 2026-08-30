import argparse
import sys

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.chunking.notion_chunker import (  # noqa: E402
    NotionPageChunkingService,
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
from app.embeddings.embedding_service import (  # noqa: E402
    EmbeddingService,
)
from app.embeddings.embedding_store import (  # noqa: E402
    EmbeddingStore,
    EmbeddingStoreError,
)
from app.integrations.notion_client import (  # noqa: E402
    NotionClient,
    NotionError,
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Notion PageをChunk・Embedding処理し、Chromaへ同期します。"
        )
    )
    parser.add_argument("page_id", help="同期対象のNotion Page ID")
    args = parser.parse_args()

    try:
        notion_client = NotionClient(
            api_token=NOTION_API_TOKEN,
            api_version=NOTION_API_VERSION,
        )
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
        result = NotionChromaSyncService(
            chunking_service=NotionPageChunkingService(
                client=notion_client
            ),
            embedding_service=embedding_service,
            embedding_store=embedding_store,
            chroma_index=chroma_index,
            model=OPENAI_EMBEDDING_MODEL,
            dimensions=OPENAI_EMBEDDING_DIMENSIONS,
        ).sync_page(args.page_id)
    except (
        NotionError,
        EmbeddingError,
        EmbeddingStoreError,
        ChromaIndexError,
    ) as error:
        print(f"Notion Chroma同期に失敗しました: {error}", file=sys.stderr)
        return 1

    print("Notion Chroma同期が完了しました。")
    print(f"Page ID: {result.notion_page_id}")
    print(f"Collection: {result.chroma_result.collection_name}")
    print(f"Current chunks: {result.chroma_result.current_chunks}")
    print(f"Embedded now: {result.embedding_result.embedded_chunks}")
    print(f"Embedding skipped: {result.embedding_result.skipped_unchanged}")
    print(f"Chroma upserted: {result.chroma_result.upserted_chunks}")
    print(f"Stale chunks deleted: {result.chroma_result.deleted_chunks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
