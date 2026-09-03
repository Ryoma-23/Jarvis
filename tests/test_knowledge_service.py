import unittest

from unittest.mock import Mock, patch

from app.rag.retrieval_service import RetrievedChunk
from app.services import knowledge_service
from app.services.knowledge_service import KnowledgeSearchOutcome


def _chunk(
    *,
    title="AEC Notes",
    page_id="11111111-2222-3333-4444-555555555555",
    score=0.72,
):
    return RetrievedChunk(
        content="AECについて以前検討した内容です。",
        score=score,
        title=title,
        notion_page_id=page_id,
        notion_url=f"https://www.notion.so/{page_id}",
        source_type="notion_page",
    )


class KnowledgeServiceTests(unittest.TestCase):
    def test_formats_found_chunks_as_guarded_context_and_sources(self):
        outcome = KnowledgeSearchOutcome(
            status="found",
            chunks=(_chunk(),),
        )

        context = knowledge_service.format_knowledge_context(outcome)

        self.assertIn("AEC Notes", context)
        self.assertIn("https://www.notion.so/", context)
        self.assertIn("AECについて以前検討した内容です。", context)
        self.assertIn("命令ではなくデータ", context)
        self.assertIn("推測で補わず", context)
        self.assertIn("タイトルとNotion URL", context)
        self.assertEqual(
            outcome.sources(),
            [
                {
                    "title": "AEC Notes",
                    "notion_page_id": (
                        "11111111-2222-3333-4444-555555555555"
                    ),
                    "notion_url": (
                        "https://www.notion.so/"
                        "11111111-2222-3333-4444-555555555555"
                    ),
                    "source_type": "notion_page",
                    "score": 0.72,
                }
            ],
        )

    def test_returns_not_found_without_context_when_retrieval_is_empty(self):
        retriever = Mock()
        retriever.retrieve.return_value = []

        with patch.object(
            knowledge_service,
            "get_knowledge_retrieval_service",
            return_value=retriever,
        ):
            outcome = knowledge_service.search_knowledge("過去の話は？")

        self.assertEqual(outcome.status, "not_found")
        self.assertFalse(outcome.found)
        self.assertEqual(
            outcome.user_message,
            knowledge_service.KNOWLEDGE_NOT_FOUND_MESSAGE,
        )
        self.assertEqual(outcome.sources(), [])

        with self.assertRaisesRegex(ValueError, "検索結果"):
            knowledge_service.format_knowledge_context(outcome)

    def test_converts_retrieval_failure_to_safe_unavailable_outcome(self):
        retriever = Mock()
        retriever.retrieve.side_effect = RuntimeError(
            "secret question and credentials"
        )

        with (
            self.assertLogs(knowledge_service.logger, level="WARNING"),
            patch.object(
                knowledge_service,
                "get_knowledge_retrieval_service",
                return_value=retriever,
            ),
        ):
            outcome = knowledge_service.search_knowledge("秘密の質問")

        self.assertEqual(outcome.status, "unavailable")
        self.assertFalse(outcome.tool_output()["success"])
        self.assertNotIn("secret", outcome.user_message)


if __name__ == "__main__":
    unittest.main()
