import unittest

from pathlib import Path


class ConversationApiContractTests(unittest.TestCase):
    def test_conversation_routes_are_registered(self):
        route = Path("app/routes/conversation.py").read_text(encoding="utf-8")
        main = Path("main.py").read_text(encoding="utf-8")

        self.assertIn('APIRouter(prefix="/conversations")', route)
        self.assertIn('@router.get("/active")', route)
        self.assertIn('@router.get("/{conversation_id}/messages")', route)
        self.assertIn('@router.post("")', route)
        self.assertIn("get_display_messages", route)
        self.assertIn("create_active_conversation", route)
        self.assertIn("app.include_router(conversation_router)", main)

    def test_browser_loads_history_and_maps_message_ids_without_inner_html(self):
        script = Path("static/script.js").read_text(encoding="utf-8")
        index = Path("static/index.html").read_text(encoding="utf-8")

        self.assertIn('requestJson("/conversations/active")', script)
        self.assertIn('requestJson("/conversations", {', script)
        self.assertIn('window.addEventListener("focus"', script)
        self.assertIn("renderConversationHistory", script)
        self.assertIn("renderConversationMessage", script)
        self.assertIn("const messageElementsById = new Map();", script)
        self.assertIn("element.dataset.messageId", script)
        self.assertIn("document.createTextNode", script)
        self.assertIn("contentElement.textContent", script)
        self.assertNotIn("innerHTML", script)
        self.assertIn('id="new-conversation-button"', index)


if __name__ == "__main__":
    unittest.main()
