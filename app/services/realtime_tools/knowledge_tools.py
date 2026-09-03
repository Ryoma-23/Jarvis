from app.services.knowledge_service import search_knowledge
from app.services.realtime_tools.common import failure


def tool_search_knowledge(arguments: dict):
    question = arguments.get("question")

    if not isinstance(question, str) or not question.strip():
        return failure("検索する質問がありません。")

    return search_knowledge(question.strip()).tool_output()
