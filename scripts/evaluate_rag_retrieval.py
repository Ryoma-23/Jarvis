import argparse
import sys

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.config import (  # noqa: E402
    CHROMA_PERSIST_DIRECTORY,
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_DIMENSIONS,
    OPENAI_EMBEDDING_MODEL,
    RAG_RETRIEVAL_MAX_CONTEXT_TOKENS,
    RAG_RETRIEVAL_MIN_SCORE,
    RAG_RETRIEVAL_TOP_K,
)
from app.integrations.openai_embedding_client import (  # noqa: E402
    EmbeddingError,
    OpenAIEmbeddingClient,
)
from app.rag.retrieval_service import (  # noqa: E402
    RagRetrievalError,
    RagRetrievalService,
    estimate_retrieved_tokens,
)
from app.vector.chroma_index import (  # noqa: E402
    ChromaIndex,
    ChromaIndexError,
)


EVALUATION_QUESTIONS = (
    "前にAECについてどう考えてた？",
    "最近後回しにしてた開発作業は？",
    "気分で音楽を選ぶ機能について考えたことは？",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ChromaのRAG検索を回答生成なしで評価します。"
    )
    parser.add_argument(
        "--question",
        action="append",
        help="固定ケースの代わりに評価する質問（複数指定可能）",
    )
    args = parser.parse_args()
    questions = tuple(args.question or EVALUATION_QUESTIONS)
    chroma_index = None
    exit_code = 0

    try:
        chroma_index = ChromaIndex(
            model=OPENAI_EMBEDDING_MODEL,
            dimensions=OPENAI_EMBEDDING_DIMENSIONS,
            persistence_path=CHROMA_PERSIST_DIRECTORY,
            create_if_missing=False,
        )
        retriever = RagRetrievalService(
            embedding_client=OpenAIEmbeddingClient(api_key=OPENAI_API_KEY),
            chroma_index=chroma_index,
            model=OPENAI_EMBEDDING_MODEL,
            dimensions=OPENAI_EMBEDDING_DIMENSIONS,
            top_k=RAG_RETRIEVAL_TOP_K,
            min_score=RAG_RETRIEVAL_MIN_SCORE,
            max_context_tokens=RAG_RETRIEVAL_MAX_CONTEXT_TOKENS,
        )

        print("RAG検索単体評価を開始します。")
        print(f"Collection: {chroma_index.collection_name}")
        print(f"Top K: {RAG_RETRIEVAL_TOP_K}")
        print(f"Minimum score: {RAG_RETRIEVAL_MIN_SCORE}")
        print(
            "Maximum context token upper bound: "
            f"{RAG_RETRIEVAL_MAX_CONTEXT_TOKENS}"
        )

        for question_index, question in enumerate(questions, start=1):
            results = retriever.retrieve(question)
            print(f"\n[{question_index}] Question: {question}")
            print(f"Retrieved: {len(results)}")
            print(
                "Context token upper bound: "
                f"{estimate_retrieved_tokens(results)}"
            )

            if not results:
                print("  閾値以上のChunkはありません。")
                continue

            for rank, result in enumerate(results, start=1):
                print(f"  {rank}. score={result.score:.4f}")
                print(f"     title={result.title}")
                print(f"     page_id={result.notion_page_id}")
                print(f"     source_type={result.source_type}")
                print(f"     url={result.notion_url}")
                print("     content:")
                print(_indent(result.content, "       "))
    except (EmbeddingError, ChromaIndexError, RagRetrievalError) as error:
        print(f"RAG検索単体評価に失敗しました: {error}", file=sys.stderr)
        exit_code = 1
    finally:
        if chroma_index is not None:
            try:
                chroma_index.close()
            except ChromaIndexError as error:
                print(
                    f"Chroma終了処理に失敗しました: {error}",
                    file=sys.stderr,
                )
                exit_code = 1

    return exit_code


def _indent(value: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" for line in value.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
