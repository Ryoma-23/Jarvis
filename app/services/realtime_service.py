from datetime import datetime

import requests

from app.openai_client import api_key
from app.config import SYSTEM_PROMPT_PATH
from app.services.memory_service import format_memory_for_prompt
from app.services.realtime_tools.tool_definitions import REALTIME_TOOL_DEFINITIONS


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

音声でメモ操作を依頼された場合は、以下のtoolを使用してください。

- メモして、メモに残して → add_note
- メモ一覧、メモ見せて、保存しているメモ → list_notes
- 〇〇のメモある？、〇〇のメモ探して → search_notes
- 〇番のメモを削除、〇番消して → delete_notes

tool実行後は、実行結果を自然な日本語で短く伝えてください。
削除は番号指定がある場合のみ実行してください。
番号がない場合は、先に一覧または検索を促してください。

音声でタスク操作を依頼された場合は、以下のtoolを使用してください。

- タスク追加、やること追加、TODO追加 → add_task
- タスク一覧、やること見せて → list_tasks
- 未完了タスク、まだ終わってないタスク → list_tasks / status_filter: todo
- 完了済みタスク → list_tasks / status_filter: done
- 〇〇のタスクある？ → search_tasks
- 〇番終わった、〇番完了 → complete_tasks
- 〇番のタスク削除、〇番消して → delete_tasks

tool実行後は、実行結果を自然な日本語で短く伝えてください。
削除や完了は番号指定がある場合のみ実行してください。
番号がない場合は、先に一覧または検索を促してください。

音声で長期記憶操作を依頼された場合は、以下のtoolを使用してください。

- 覚えておいて、今後のために覚えて、今後の会話で使って → add_memory
- 覚えていること見せて、記憶一覧、長期記憶一覧 → list_memory
- 〇〇について覚えてる？、〇〇の記憶ある？ → search_memory
- 〇番の記憶を更新、〇番を〜に変えて → update_memory
- 〇番の記憶を削除、〇番の記憶を消して → delete_memory

長期記憶は、今後の会話でJarvisが参考にするユーザー情報です。
一時的な予定はメモ、実行する行動はタスク、継続的なユーザー情報は長期記憶として扱ってください。

tool実行後は、実行結果を自然な日本語で短く伝えてください。
削除や更新は番号指定がある場合のみ実行してください。
番号がない場合は、先に一覧または検索を促してください。
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
                "tools": REALTIME_TOOL_DEFINITIONS,
                "tool_choice": "auto",
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