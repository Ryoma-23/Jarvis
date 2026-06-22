import json

from app.config import (
    NOTE_INTENT_PROMPT_PATH,
    TASK_INTENT_PROMPT_PATH,
    MEMORY_INTENT_PROMPT_PATH
)
from app.openai_client import client
from app.services.note_service import (
    add_note,
    format_notes_list,
    search_notes,
    delete_notes,
    delete_all_notes
)
from app.services.task_service import (
    add_task,
    format_tasks_list,
    search_tasks,
    complete_tasks,
    delete_tasks
)
from app.services.memory_service import (
    add_memory,
    format_memory_list,
    search_memory,
    delete_memory,
    update_memory
)


pending_delete_all = False


def load_prompt(path):
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def classify_note_intent(message: str):
    note_prompt = load_prompt(NOTE_INTENT_PROMPT_PATH)

    response = client.responses.create(
        model="gpt-5-mini",
        input=f"{note_prompt}\n\nユーザー入力:\n{message}",
        reasoning={"effort": "low"},
    )

    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError:
        return {
            "action": "none",
            "content": None,
            "keyword": None,
            "note_ids": []
        }


def handle_note_intent(message: str):
    global pending_delete_all

    if pending_delete_all:
        if message.strip() in [
            "はい",
            "OK",
            "ok",
            "実行",
            "削除",
            "削除して",
            "消して"
        ]:
            pending_delete_all = False
            return delete_all_notes()

        if message.strip() in [
            "いいえ",
            "キャンセル",
            "やめる"
        ]:
            pending_delete_all = False
            return "全削除をキャンセルしました。"

    if (
        "メモ全削除" in message
        or "すべてのメモを削除" in message
        or "全てのメモを削除" in message
        or "メモを全部削除" in message
        or "メモ全部削除" in message
        or "メモを全部消して" in message
        or "メモ全部消して" in message
    ):
        pending_delete_all = True
        return "現在保存されているメモをすべて削除します。よろしいですか？"

    result = classify_note_intent(message)
    action = result.get("action")

    if action == "add":
        content = result.get("content")

        if not content:
            return "メモする内容が見つかりませんでした。"

        note = add_note(content)

        return f'メモしておきました。\n{note["id"]}. {note["content"]}'

    if action == "list":
        return format_notes_list()

    if action == "search":
        keyword = result.get("keyword")

        if not keyword:
            return "探すキーワードを教えてください。"

        return search_notes(keyword)

    if action == "delete":
        delete_all = result.get("delete_all", False)
        note_ids = result.get("note_ids", [])

        if delete_all:
            return delete_all_notes()

        if not note_ids:
            return "削除するメモ番号を教えてください。"

        try:
            note_ids = [int(note_id) for note_id in note_ids]
        except ValueError:
            return "削除するメモ番号を正しく読み取れませんでした。例：3番のメモを削除、3,4,5番を削除"

        return delete_notes(note_ids)

    return None


def classify_task_intent(message: str):
    task_prompt = load_prompt(TASK_INTENT_PROMPT_PATH)

    response = client.responses.create(
        model="gpt-5-mini",
        input=f"{task_prompt}\n\nユーザー入力:\n{message}",
        reasoning={"effort": "low"},
    )

    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError:
        return {
            "action": "none",
            "title": None,
            "keyword": None,
            "task_ids": [],
            "status_filter": None,
            "due_date": None
        }


def handle_task_intent(message: str):
    result = classify_task_intent(message)
    action = result.get("action")

    if action == "add":
        title = result.get("title")
        due_date = result.get("due_date")

        if not title:
            return "追加するタスク内容が見つかりませんでした。"

        task = add_task(title, due_date)

        due = task["due_date"] if task["due_date"] else "期限なし"
        return f'タスクに追加しました。\n{task["id"]}. {task["title"]} / 期限: {due}'

    if action == "list":
        status_filter = result.get("status_filter") or "all"
        return format_tasks_list(status_filter)

    if action == "search":
        keyword = result.get("keyword")

        if not keyword:
            return "探すキーワードを教えてください。"

        return search_tasks(keyword)

    if action == "complete":
        task_ids = result.get("task_ids", [])

        if not task_ids:
            return "完了にするタスク番号を教えてください。"

        task_ids = [int(task_id) for task_id in task_ids]
        return complete_tasks(task_ids)

    if action == "delete":
        task_ids = result.get("task_ids", [])

        if not task_ids:
            return "削除するタスク番号を教えてください。"

        task_ids = [int(task_id) for task_id in task_ids]
        return delete_tasks(task_ids)

    return None


def classify_memory_intent(message: str):
    memory_prompt = load_prompt(MEMORY_INTENT_PROMPT_PATH)

    response = client.responses.create(
        model="gpt-5-mini",
        input=f"{memory_prompt}\n\nユーザー入力:\n{message}",
        reasoning={"effort": "low"},
    )

    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError:
        return {
            "action": "none",
            "content": None,
            "category": None,
            "keyword": None,
            "memory_ids": []
        }


def handle_memory_intent(message: str):
    result = classify_memory_intent(message)
    action = result.get("action")

    if action == "add":
        content = result.get("content")
        category = result.get("category") or "other"

        if not content:
            return "覚える内容が見つかりませんでした。"

        memory = add_memory(content, category)

        return f'覚えておきました。\n{memory["id"]}. [{memory["category"]}] {memory["content"]}'

    if action == "list":
        return format_memory_list()

    if action == "search":
        keyword = result.get("keyword")

        if not keyword:
            return "探すキーワードを教えてください。"

        return search_memory(keyword)

    if action == "delete":
        memory_ids = result.get("memory_ids", [])

        if not memory_ids:
            return "削除する記憶番号を教えてください。"

        memory_ids = [int(memory_id) for memory_id in memory_ids]
        return delete_memory(memory_ids)

    if action == "update":
        memory_ids = result.get("memory_ids", [])
        content = result.get("content")
        category = result.get("category")

        if not memory_ids:
            return "更新する記憶番号を教えてください。"

        if not content:
            return "更新後の内容を教えてください。"

        memory_ids = [int(memory_id) for memory_id in memory_ids]
        return update_memory(memory_ids, content, category)

    return None