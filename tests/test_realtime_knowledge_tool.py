import unittest

from unittest.mock import patch

from app.rag.retrieval_service import RetrievedChunk
from app.services import realtime_service
from app.services.knowledge_service import KnowledgeSearchOutcome
from app.services.realtime_tool_service import execute_realtime_tool
from app.services.realtime_tools import knowledge_tools
from app.services.realtime_tools.tool_definitions import (
    REALTIME_TOOL_DEFINITIONS,
)
from app.services.realtime_tools.tool_registry import TOOL_REGISTRY


class RealtimeKnowledgeToolTests(unittest.TestCase):
    def test_definition_and_registry_include_search_knowledge(self):
        definitions = {
            definition["name"]: definition
            for definition in REALTIME_TOOL_DEFINITIONS
        }

        self.assertIn("search_knowledge", definitions)
        self.assertIn("search_knowledge", TOOL_REGISTRY)
        self.assertEqual(
            definitions["search_knowledge"]["parameters"]["required"],
            ["question"],
        )

        with (
            patch.object(
                realtime_service,
                "load_system_prompt",
                return_value="system",
            ),
            patch.object(
                realtime_service,
                "format_memory_for_prompt",
                return_value="memory",
            ),
        ):
            instructions = realtime_service.build_realtime_instructions()
        self.assertIn("曖昧な過去情報", instructions)
        self.assertIn("list_tasks / status_filter: todo", instructions)
        self.assertIn("found=falseの場合は推測せず", instructions)

    def test_returns_structured_retrieval_results_for_function_output(self):
        outcome = KnowledgeSearchOutcome(
            status="found",
            chunks=(
                RetrievedChunk(
                    content="過去にAECを検討しました。",
                    score=0.81,
                    title="AEC検討メモ",
                    notion_page_id="page-id",
                    notion_url="https://www.notion.so/page-id",
                    source_type="notion_page",
                ),
            ),
        )

        with patch.object(
            knowledge_tools,
            "search_knowledge",
            return_value=outcome,
        ) as search:
            result = execute_realtime_tool(
                "search_knowledge",
                {"question": "AECについて前にどう考えてた？"},
            )

        search.assert_called_once_with("AECについて前にどう考えてた？")
        self.assertTrue(result["success"])
        self.assertTrue(result["found"])
        self.assertEqual(result["results"][0]["title"], "AEC検討メモ")
        self.assertEqual(
            result["results"][0]["notion_url"],
            "https://www.notion.so/page-id",
        )

    def test_empty_question_and_no_results_do_not_invite_guessing(self):
        empty = execute_realtime_tool("search_knowledge", {})

        self.assertFalse(empty["success"])

        with patch.object(
            knowledge_tools,
            "search_knowledge",
            return_value=KnowledgeSearchOutcome(status="not_found"),
        ):
            missing = execute_realtime_tool(
                "search_knowledge",
                {"question": "過去の情報は？"},
            )

        self.assertTrue(missing["success"])
        self.assertFalse(missing["found"])
        self.assertEqual(missing["results"], [])
        self.assertIn("見つけられませんでした", missing["message"])


if __name__ == "__main__":
    unittest.main()
