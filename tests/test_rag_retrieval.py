import unittest

from unittest.mock import Mock

from app.integrations.openai_embedding_client import OpenAIEmbeddingClient
from app.rag.retrieval_service import (
    RagRetrievalError,
    RagRetrievalService,
    estimate_retrieved_tokens,
)
from app.vector.chroma_index import ChromaIndex, ChromaQueryRecord


MODEL = "text-embedding-3-small"
DIMENSIONS = 3
PAGE_ID = "11111111-2222-3333-4444-555555555555"
OTHER_PAGE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _record(
    chunk_id,
    document,
    distance,
    *,
    page_id=PAGE_ID,
    chunk_index=0,
    title="AEC Notes",
):
    return ChromaQueryRecord(
        chunk_id=chunk_id,
        document=document,
        distance=distance,
        metadata={
            "title": title,
            "notion_page_id": page_id,
            "notion_url": f"https://www.notion.so/{page_id}",
            "source_type": "notion_page",
            "chunk_index": chunk_index,
        },
    )


class RagRetrievalServiceTests(unittest.TestCase):
    def setUp(self):
        self.embedding_client = Mock(spec=OpenAIEmbeddingClient)
        self.embedding_client.create_embeddings.return_value = [
            [1.0, 0.0, 0.0]
        ]
        self.chroma_index = Mock(spec=ChromaIndex)
        self.chroma_index.model = MODEL
        self.chroma_index.dimensions = DIMENSIONS

    def _service(
        self,
        *,
        top_k=5,
        min_score=0.35,
        max_context_tokens=2000,
    ):
        return RagRetrievalService(
            embedding_client=self.embedding_client,
            chroma_index=self.chroma_index,
            model=MODEL,
            dimensions=DIMENSIONS,
            top_k=top_k,
            min_score=min_score,
            max_context_tokens=max_context_tokens,
        )

    def test_embeds_question_filters_and_merges_nearby_page_chunks(self):
        self.chroma_index.query.return_value = [
            _record("chunk-1", "# AEC\n\nSecond thought", 0.1, chunk_index=1),
            _record("chunk-0", "# AEC\n\nFirst thought", 0.2, chunk_index=0),
            _record("duplicate", "# AEC\n\nFirst thought", 0.3),
            _record(
                "other",
                "Music should match the user's mood.",
                0.5,
                page_id=OTHER_PAGE_ID,
                title="Mood Music",
            ),
            _record("below-threshold", "Unrelated", 3.0, chunk_index=4),
        ]

        results = self._service().retrieve(
            "前にAECについてどう考えてた？"
        )

        self.embedding_client.create_embeddings.assert_called_once_with(
            ["前にAECについてどう考えてた？"],
            model=MODEL,
            dimensions=DIMENSIONS,
        )
        self.chroma_index.query.assert_called_once_with(
            [1.0, 0.0, 0.0],
            n_results=5,
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].notion_page_id, PAGE_ID)
        self.assertEqual(results[0].content.count("# AEC"), 1)
        self.assertIn("First thought", results[0].content)
        self.assertIn("Second thought", results[0].content)
        self.assertAlmostEqual(results[0].score, 1.0 / 1.1)
        self.assertEqual(
            set(results[0].to_dict()),
            {
                "content",
                "score",
                "title",
                "notion_page_id",
                "notion_url",
                "source_type",
            },
        )

    def test_does_not_merge_nonadjacent_chunks_from_same_page(self):
        self.chroma_index.query.return_value = [
            _record("chunk-0", "First", 0.1, chunk_index=0),
            _record("chunk-2", "Third", 0.2, chunk_index=2),
        ]

        results = self._service(top_k=2).retrieve("question")

        self.assertEqual(
            [result.content for result in results],
            ["First", "Third"],
        )

    def test_applies_conservative_total_context_token_limit(self):
        self.chroma_index.query.return_value = [
            _record("long", "あいうえおかきくけこ", 0.1, title="T"),
            _record(
                "second",
                "Second result",
                0.2,
                page_id=OTHER_PAGE_ID,
                title="U",
            ),
        ]

        results = self._service(
            top_k=2,
            max_context_tokens=10,
        ).retrieve("question")

        self.assertTrue(results)
        self.assertLessEqual(estimate_retrieved_tokens(results), 10)
        self.assertTrue(results[0].content.endswith("…"))

    def test_rejects_empty_question_before_external_calls(self):
        with self.assertRaisesRegex(RagRetrievalError, "質問が空"):
            self._service().retrieve("   ")

        self.embedding_client.create_embeddings.assert_not_called()
        self.chroma_index.query.assert_not_called()

    def test_rejects_incomplete_chroma_metadata(self):
        record = _record("chunk", "Content", 0.1)
        record.metadata.pop("notion_url")
        self.chroma_index.query.return_value = [record]

        with self.assertRaisesRegex(RagRetrievalError, "notion_url"):
            self._service(top_k=1).retrieve("question")


if __name__ == "__main__":
    unittest.main()
