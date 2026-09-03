import json

from app.config import ROUTER_INTENT_PROMPT_PATH
from app.openai_client import client


VALID_ROUTES = {
    "chat",
    "note",
    "task",
    "memory",
    "knowledge_search",
}

KNOWLEDGE_RECALL_CUES = (
    "どう考えてた",
    "どう思ってた",
    "考えたこと",
    "話してた",
    "話したこと",
    "言ってた",
    "決めてた",
    "検討してた",
    "後回しにしてた",
    "何だっけ",
    "なんだっけ",
)


def load_router_prompt():
    with open(ROUTER_INTENT_PROMPT_PATH, "r", encoding="utf-8") as file:
        return file.read()


def route_message(message: str):
    # 固定判定
    quick_route = quick_route_message(message)

    if quick_route:
        return quick_route

    # 迷った時にAI判定
    router_prompt = load_router_prompt()

    response = client.responses.create(
        model="gpt-5-mini",
        input=f"{router_prompt}\n\nユーザー入力:\n{message}",
        reasoning={"effort": "low"},
    )

    try:
        result = json.loads(response.output_text)
        route = result.get("route") if isinstance(result, dict) else None
        return (
            route
            if isinstance(route, str) and route in VALID_ROUTES
            else "chat"
        )

    except (json.JSONDecodeError, TypeError):
        return "chat"


def quick_route_message(message: str):
    structured_route = _structured_storage_route(message)

    if structured_route:
        return structured_route

    if any(cue in message for cue in KNOWLEDGE_RECALL_CUES):
        return "knowledge_search"

    if "メモ" in message:
        return "note"

    if "タスク" in message or "TODO" in message or "やること" in message:
        return "task"

    if "覚えて" in message or "記憶" in message:
        return "memory"

    return None


def _structured_storage_route(message: str) -> str | None:
    note_cues = (
        "メモして",
        "メモに残",
        "メモ一覧",
        "メモ見せ",
        "メモ検索",
        "メモ探",
        "メモを探",
        "メモ削除",
        "メモを削除",
        "メモ消",
        "メモを消",
    )

    if any(cue in message for cue in note_cues):
        return "note"

    if "TODO" in message or "やること" in message:
        return "task"

    task_actions = (
        "追加",
        "一覧",
        "見せ",
        "未完了",
        "完了",
        "終わ",
        "削除",
        "消して",
        "検索",
        "探して",
        "期限",
        "今日",
    )

    if "タスク" in message and any(
        action in message for action in task_actions
    ):
        return "task"

    memory_cues = (
        "覚えておいて",
        "覚えてる",
        "覚えている",
        "記憶一覧",
        "長期記憶一覧",
        "記憶検索",
        "記憶削除",
        "記憶を削除",
        "記憶更新",
        "記憶を更新",
    )

    if any(cue in message for cue in memory_cues):
        return "memory"

    return None
