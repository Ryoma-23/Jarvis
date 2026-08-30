import sys

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.config import (  # noqa: E402
    CHROMA_PERSIST_DIRECTORY,
    NOTION_API_TOKEN,
    NOTION_API_VERSION,
    OPENAI_EMBEDDING_DIMENSIONS,
    OPENAI_EMBEDDING_MODEL,
)
from app.integrations.notion_client import (  # noqa: E402
    NotionClient,
    NotionError,
)
from app.vector.chroma_index import (  # noqa: E402
    ChromaIndex,
    ChromaIndexError,
)
from app.vector.notion_chroma_sync import (  # noqa: E402
    ChromaNotionPageAuditor,
)


def main() -> int:
    try:
        chroma_index = ChromaIndex(
            model=OPENAI_EMBEDDING_MODEL,
            dimensions=OPENAI_EMBEDDING_DIMENSIONS,
            persistence_path=CHROMA_PERSIST_DIRECTORY,
            create_if_missing=False,
        )
        indexed_pages = chroma_index.list_indexed_pages()
        missing_pages = ChromaNotionPageAuditor(
            notion_client=NotionClient(
                api_token=NOTION_API_TOKEN,
                api_version=NOTION_API_VERSION,
            ),
            chroma_index=chroma_index,
        ).find_missing_pages()
    except (NotionError, ChromaIndexError) as error:
        print(f"Chroma Page監査に失敗しました: {error}", file=sys.stderr)
        return 1

    print("Chroma Page監査が完了しました。")
    print(f"Collection: {chroma_index.collection_name}")
    print(f"Indexed pages: {len(indexed_pages)}")
    print(f"Missing/trashed pages: {len(missing_pages)}")

    for page in missing_pages:
        print(
            f"Page ID: {page.notion_page_id} / "
            f"reason: {page.reason} / chunks: {len(page.chunk_ids)}"
        )

        for chunk_id in page.chunk_ids:
            print(f"  Chunk ID: {chunk_id}")

    print("監査は読み取り専用です。Chromaからは削除していません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
