import hashlib
import sys
import tempfile

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.chunking.notion_chunker import NotionChunk  # noqa: E402
from app.config import (  # noqa: E402
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
from app.integrations.openai_embedding_client import (  # noqa: E402
    EmbeddingError,
    EmbeddingResponseError,
    OpenAIEmbeddingClient,
)


def verify_embedding() -> tuple[int, int, int]:
    client = OpenAIEmbeddingClient(api_key=OPENAI_API_KEY)

    with tempfile.TemporaryDirectory() as temporary_directory:
        store = EmbeddingStore(
            Path(temporary_directory) / "embeddings.sqlite3"
        )
        service = EmbeddingService(
            client=client,
            store=store,
            model=OPENAI_EMBEDDING_MODEL,
            dimensions=OPENAI_EMBEDDING_DIMENSIONS,
            batch_size=min(2, OPENAI_EMBEDDING_BATCH_SIZE),
        )
        chunks = [
            _chunk(0, "JARVIS Phase 6 embedding verification."),
            _chunk(1, "Stable chunks should not be embedded twice."),
            _chunk(2, "   "),
        ]
        first = service.embed_chunks(chunks)
        second = service.embed_chunks(chunks)
        records = store.list_records()

        if (
            first.embedded_chunks != 2
            or first.excluded_empty != 1
            or second.embedded_chunks != 0
            or second.skipped_unchanged != 2
            or second.excluded_empty != 1
            or len(records) != 2
        ):
            raise EmbeddingResponseError(
                "Embeddingの初回生成または再実行スキップ結果が不正です。"
            )

        if any(
            len(record["embedding"]) != OPENAI_EMBEDDING_DIMENSIONS
            for record in records
        ):
            raise EmbeddingResponseError(
                "保存されたEmbeddingの次元数が一致しません。"
            )

        return (
            first.api_batches,
            len(records),
            OPENAI_EMBEDDING_DIMENSIONS,
        )


def main() -> int:
    try:
        api_batches, record_count, dimensions = verify_embedding()
    except (EmbeddingError, EmbeddingStoreError) as error:
        print(f"Embedding確認に失敗しました: {error}", file=sys.stderr)
        return 1

    print("Embedding確認に成功しました。")
    print(f"Model: {OPENAI_EMBEDDING_MODEL}")
    print(f"Dimensions: {dimensions}")
    print(f"Initial API batches: {api_batches}")
    print(f"Stored records: {record_count}")
    print("Second run embedded: 0 (unchanged records skipped)")
    print("Verification Storeは一時ディレクトリから削除済みです。")
    return 0


def _chunk(index: int, content: str) -> NotionChunk:
    return NotionChunk(
        chunk_id=f"notion-chunk:embedding-verification-{index}",
        notion_page_id="embedding-verification-page",
        block_id=f"embedding-verification-block-{index}",
        title="Embedding Verification",
        chunk_index=index,
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        last_edited_time="2026-08-30T00:00:00+00:00",
        source_type="notion_page",
        notion_url="https://www.notion.so/embedding-verification",
        heading_path=("Embedding Verification",),
        block_ids=(f"embedding-verification-block-{index}",),
    )


if __name__ == "__main__":
    raise SystemExit(main())
