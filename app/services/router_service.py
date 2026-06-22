import json

from app.config import ROUTER_INTENT_PROMPT_PATH
from app.openai_client import client


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
        return result.get("route", "chat")

    except json.JSONDecodeError:
        return "chat"


def quick_route_message(message: str):
    if "メモ" in message:
        return "note"

    if "タスク" in message or "TODO" in message or "やること" in message:
        return "task"

    if "覚えて" in message or "記憶" in message:
        return "memory"

    return None