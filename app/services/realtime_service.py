from datetime import datetime

import requests

from app.openai_client import api_key
from app.config import SYSTEM_PROMPT_PATH
from app.services.memory_service import format_memory_for_prompt


def load_system_prompt():
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as file:
        return file.read()


def build_realtime_instructions():
    system_prompt = load_system_prompt()

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")

    memory_context = format_memory_for_prompt()

    return f"""
{system_prompt}

現在日時:
{current_time}

長期記憶:
{memory_context}

音声会話ルール:
- 必ず日本語で返答する
- 返答はテキスト会話より短く話す
- 不要な会話はしない
- 聞き取れないときは反応しない
- 長文説明が必要な場合は、まず要点だけ話す
- 箇条書きではなく、自然な会話として話す
"""


def create_realtime_token():
    instructions = build_realtime_instructions()

    response = requests.post(
        "https://api.openai.com/v1/realtime/client_secrets",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "session": {
                "type": "realtime",
                "model": "gpt-realtime-2",
                "instructions": instructions,
                "audio": {
                    "output": {
                        "voice": "cedar",
                    }
                }
            }
        }
    )

    response.raise_for_status()

    return response.json()