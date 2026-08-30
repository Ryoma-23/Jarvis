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
    EMBEDDINGS_DB_FILE,
    NOTION_API_TOKEN,
    NOTION_API_VERSION,
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_BATCH_SIZE,
    OPENAI_EMBEDDING_DIMENSIONS,
    OPENAI_EMBEDDING_MODEL,
)
from app.embeddings.embedding_service import (  # noqa: E402
    EmbeddingRunResult,
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


def embed_notion_page(
    page_id: str,
    *,
    notion_client: NotionClient,
    embedding_client: OpenAIEmbeddingClient,
    store: EmbeddingStore,
    model: str,
    dimensions: int,
    batch_size: int,
) -> EmbeddingRunResult:
    chunks = NotionPageChunkingService(
        client=notion_client
    ).chunk_page(page_id)
    return EmbeddingService(
        client=embedding_client,
        store=store,
        model=model,
        dimensions=dimensions,
        batch_size=batch_size,
    ).embed_chunks(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Notion PageをChunk化し、未生成のEmbeddingをローカルへ保存します。"
        )
    )
    parser.add_argument(
        "page_id",
        help="Embedding対象のNotion Page ID",
    )
    args = parser.parse_args()

    try:
        result = embed_notion_page(
            args.page_id,
            notion_client=NotionClient(
                api_token=NOTION_API_TOKEN,
                api_version=NOTION_API_VERSION,
            ),
            embedding_client=OpenAIEmbeddingClient(
                api_key=OPENAI_API_KEY,
            ),
            store=EmbeddingStore(EMBEDDINGS_DB_FILE),
            model=OPENAI_EMBEDDING_MODEL,
            dimensions=OPENAI_EMBEDDING_DIMENSIONS,
            batch_size=OPENAI_EMBEDDING_BATCH_SIZE,
        )
    except (NotionError, EmbeddingError, EmbeddingStoreError) as error:
        print(f"Notion Page Embeddingに失敗しました: {error}", file=sys.stderr)
        return 1

    print("Notion Page Embeddingが完了しました。")
    print(f"Total chunks: {result.total_chunks}")
    print(f"Embedded: {result.embedded_chunks}")
    print(f"Skipped unchanged: {result.skipped_unchanged}")
    print(f"Excluded empty: {result.excluded_empty}")
    print(f"API batches: {result.api_batches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
