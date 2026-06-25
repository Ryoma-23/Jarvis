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
                "tools": [
                    {
                        "type": "function",
                        "name": "add_note",
                        "description": "ユーザーのメモを保存します。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "保存するメモ内容"
                                }
                            },
                            "required": ["content"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "list_notes",
                        "description": "保存されているメモ一覧を取得します。",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "type": "function",
                        "name": "search_notes",
                        "description": "キーワードに一致するメモを検索します。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "keyword": {
                                    "type": "string",
                                    "description": "検索キーワード"
                                }
                            },
                            "required": ["keyword"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "delete_notes",
                        "description": "指定した番号のメモを削除します。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "note_ids": {
                                    "type": "array",
                                    "items": {
                                        "type": "integer"
                                    },
                                    "description": "削除するメモIDの配列"
                                }
                            },
                            "required": ["note_ids"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "add_task",
                        "description": "ユーザーのタスクを追加します。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "追加するタスク名"
                                },
                                "due_date": {
                                    "type": ["string", "null"],
                                    "description": "期限。YYYY-MM-DD形式。なければnull"
                                }
                            },
                            "required": ["title"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "list_tasks",
                        "description": "保存されているタスク一覧を取得します。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "status_filter": {
                                    "type": "string",
                                    "enum": ["all", "todo", "done"],
                                    "description": "all=全件、todo=未完了、done=完了済み"
                                }
                            },
                            "required": ["status_filter"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "search_tasks",
                        "description": "キーワードに一致するタスクを検索します。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "keyword": {
                                    "type": "string",
                                    "description": "検索キーワード"
                                }
                            },
                            "required": ["keyword"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "complete_tasks",
                        "description": "指定したタスクを完了にします。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task_ids": {
                                    "type": "array",
                                    "items": {
                                        "type": "integer"
                                    },
                                    "description": "完了にするタスクIDの配列"
                                }
                            },
                            "required": ["task_ids"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "delete_tasks",
                        "description": "指定したタスクを削除します。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task_ids": {
                                    "type": "array",
                                    "items": {
                                        "type": "integer"
                                    },
                                    "description": "削除するタスクIDの配列"
                                }
                            },
                            "required": ["task_ids"]
                        }
                    }
                ],
                
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