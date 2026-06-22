import os
import json
import re

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path


# .envファイルを読み込む
load_dotenv()

# OpenAI APIキーを取得
api_key = os.getenv("OPENAI_API_KEY")

# APIキーがない場合はエラー
if not api_key:
    raise RuntimeError("OPENAI_API_KEY が設定されていません。.env を確認してください。")

# OpenAIクライアントを作成
client = OpenAI(api_key=api_key)

# 会話履歴用リストを作成
conversation_history = []

# 履歴件数制限
MAX_HISTORY = 30

# 全件削除確認フラグ
pending_delete_all = False

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
NOTES_FILE = DATA_DIR / "notes.json"
TASKS_FILE = DATA_DIR / "tasks.json"
MEMORY_FILE = DATA_DIR / "memory.json"

SYSTEM_PROMPT_PATH = BASE_DIR / "prompts" / "system_prompt.txt"
NOTE_INTENT_PROMPT_PATH = BASE_DIR / "prompts" / "note_intent_prompt.txt"
TASK_INTENT_PROMPT_PATH = BASE_DIR / "prompts" / "task_intent_prompt.txt"
MEMORY_INTENT_PROMPT_PATH = BASE_DIR / "prompts" / "memory_intent_prompt.txt"

# FastAPIアプリを作成
app = FastAPI()

# staticフォルダを配信対象にする
app.mount("/static", StaticFiles(directory="static"), name="static")

# 短期記憶関数
def trim_history():
    global conversation_history

    if len(conversation_history) > MAX_HISTORY:
        conversation_history = conversation_history[-MAX_HISTORY:]

# システムプロンプト読み込み（人格）
def load_system_prompt():
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as file:
        return file.read()

def load_note_intent_prompt():
    with open(NOTE_INTENT_PROMPT_PATH, "r", encoding="utf-8") as file:
        return file.read()
    
# notes.json 初期化関数
def init_notes_file():
    DATA_DIR.mkdir(exist_ok=True)

    if not NOTES_FILE.exists():
        with open(NOTES_FILE, "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=2)

# メモ読み込み関数
def load_notes():
    init_notes_file()

    with open(NOTES_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

# メモ保存関数
def save_notes(notes):
    init_notes_file()

    with open(NOTES_FILE, "w", encoding="utf-8") as file:
        json.dump(notes, file, ensure_ascii=False, indent=2)

# メモ追加関数
def add_note(content):
    notes = load_notes()

    next_id = 1

    if notes:
        next_id = max(note["id"] for note in notes) + 1

    note = {
        "id": next_id,
        "content": content,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    notes.append(note)

    save_notes(notes)

    return note

# メモ一覧関数
def format_notes_list():
    notes = load_notes()

    if not notes:
        return "まだメモはありません。"

    lines = ["現在のメモはこちらです。"]

    for note in notes:
        lines.append(
            f'{note["id"]}. {note["content"]}（{note["created_at"]}）'
        )

    return "\n".join(lines)

# メモ検索関数
def search_notes(keyword):
    notes = load_notes()

    results = [
        note for note in notes
        if keyword.lower() in note["content"].lower()
    ]

    if not results:
        return f"「{keyword}」に関するメモは見つかりませんでした。"

    lines = [f"「{keyword}」に関するメモはこちらです。"]

    for note in results:
        lines.append(
            f'{note["id"]}. {note["content"]}（{note["created_at"]}）'
        )

    return "\n".join(lines)

# メモ削除関数
def delete_note(note_id):
    notes = load_notes()

    new_notes = [
        note for note in notes
        if note["id"] != note_id
    ]

    if len(notes) == len(new_notes):
        return f"{note_id}番のメモは見つかりませんでした。"

    save_notes(new_notes)

    return f"{note_id}番のメモを削除しました。"

# メモAI判定関数
def classify_note_intent(message: str):
    note_prompt = load_note_intent_prompt()

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
            "note_id": None
        }

# メモAI判定結果処理関数
def handle_note_intent(message: str):
    global pending_delete_all

    if pending_delete_all:

        if message.strip() in [
            "はい",
            "OK",
            "ok",
            "実行",
            "削除",
            "削除して"
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

        return(
            "現在保存されているメモをすべて削除します。よろしいですか？"
        )
    
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

# メモ複数削除
def delete_notes(note_ids):
    notes = load_notes()

    deleted_notes = [
        note for note in notes
        if note["id"] in note_ids
    ]

    if not deleted_notes:
        return "指定されたメモは見つかりませんでした。"

    new_notes = [
        note for note in notes
        if note["id"] not in note_ids
    ]

    save_notes(new_notes)

    deleted_ids = ", ".join(str(note["id"]) for note in deleted_notes)

    return f"{deleted_ids}番のメモを削除しました。"

# メモ全削除
def delete_all_notes():
    notes = load_notes()

    if not notes:
        return "削除するメモはありません。"

    save_notes([])

    return "すべてのメモを削除しました。"

# tasks.json初期化
def init_tasks_file():
    DATA_DIR.mkdir(exist_ok=True)

    if not TASKS_FILE.exists():
        with open(TASKS_FILE, "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=2)

# タスク読み込み・保存
def load_tasks():
    init_tasks_file()

    with open(TASKS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

def save_tasks(tasks):
    init_tasks_file()

    with open(TASKS_FILE, "w", encoding="utf-8") as file:
        json.dump(tasks, file, ensure_ascii=False, indent=2)

# タスク追加
def add_task(title, due_date=None):
    tasks = load_tasks()

    next_id = 1
    if tasks:
        next_id = max(task["id"] for task in tasks) + 1

    task = {
        "id": next_id,
        "title": title,
        "status": "todo",
        "due_date": due_date,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "completed_at": None
    }

    tasks.append(task)
    save_tasks(tasks)

    return task

# タスク一覧
def format_tasks_list(status_filter="all"):
    tasks = load_tasks()

    if status_filter == "todo":
        tasks = [task for task in tasks if task["status"] == "todo"]
        title = "未完了のタスクはこちらです。"
    elif status_filter == "done":
        tasks = [task for task in tasks if task["status"] == "done"]
        title = "完了済みのタスクはこちらです。"
    else:
        title = "現在のタスクはこちらです。"

    if not tasks:
        return "該当するタスクはありません。"

    lines = [title]

    for task in tasks:
        status = "未完了" if task["status"] == "todo" else "完了"
        due = task["due_date"] if task["due_date"] else "期限なし"
        lines.append(f'{task["id"]}. {task["title"]} / {status} / 期限: {due}')

    return "\n".join(lines)

# タスク検索
def search_tasks(keyword):
    tasks = load_tasks()

    results = [
        task for task in tasks
        if keyword.lower() in task["title"].lower()
    ]

    if not results:
        return f"「{keyword}」に関するタスクは見つかりませんでした。"

    lines = [f"「{keyword}」に関するタスクはこちらです。"]

    for task in results:
        status = "未完了" if task["status"] == "todo" else "完了"
        due = task["due_date"] if task["due_date"] else "期限なし"
        lines.append(f'{task["id"]}. {task["title"]} / {status} / 期限: {due}')

    return "\n".join(lines)

# タスク完了処理
def complete_tasks(task_ids):
    tasks = load_tasks()

    completed = []

    for task in tasks:
        if task["id"] in task_ids:
            task["status"] = "done"
            task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            completed.append(task["id"])

    if not completed:
        return "指定されたタスクは見つかりませんでした。"

    save_tasks(tasks)

    ids = ", ".join(str(task_id) for task_id in completed)
    return f"{ids}番のタスクを完了にしました。"

# タスク削除処理
def delete_tasks(task_ids):
    tasks = load_tasks()

    deleted = [
        task for task in tasks
        if task["id"] in task_ids
    ]

    if not deleted:
        return "指定されたタスクは見つかりませんでした。"

    new_tasks = [
        task for task in tasks
        if task["id"] not in task_ids
    ]

    save_tasks(new_tasks)

    ids = ", ".join(str(task["id"]) for task in deleted)
    return f"{ids}番のタスクを削除しました。"

# タスク意図判定
def load_task_intent_prompt():
    with open(TASK_INTENT_PROMPT_PATH, "r", encoding="utf-8") as file:
        return file.read()


def classify_task_intent(message: str):
    task_prompt = load_task_intent_prompt()

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
    
# タスク判定結果処理
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

# memory.json初期化
def init_memory_file():
    DATA_DIR.mkdir(exist_ok=True)

    if not MEMORY_FILE.exists():
        with open(MEMORY_FILE, "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=2)

# 長期記憶読み込み
def load_memory():
    init_memory_file()

    with open(MEMORY_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

# 長期記憶保存
def save_memory(memories):
    init_memory_file()

    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(memories, file, ensure_ascii=False, indent=2)

# 長期記憶追加
def add_memory(content, category="other"):
    memories = load_memory()

    next_id = 1
    if memories:
        next_id = max(memory["id"] for memory in memories) + 1

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    memory = {
        "id": next_id,
        "content": content,
        "category": category or "other",
        "created_at": now,
        "updated_at": now
    }

    memories.append(memory)
    save_memory(memories)

    return memory

# 長期記憶一覧
def format_memory_list():
    memories = load_memory()

    if not memories:
        return "まだ覚えていることはありません。"

    lines = ["現在覚えていることはこちらです。"]

    for memory in memories:
        lines.append(
            f'{memory["id"]}. [{memory["category"]}] {memory["content"]}'
        )

    return "\n".join(lines)

# 長期記憶検索
def search_memory(keyword):
    memories = load_memory()

    results = [
        memory for memory in memories
        if keyword.lower() in memory["content"].lower()
        or keyword.lower() in memory["category"].lower()
    ]

    if not results:
        return f"「{keyword}」に関する記憶は見つかりませんでした。"

    lines = [f"「{keyword}」に関する記憶はこちらです。"]

    for memory in results:
        lines.append(
            f'{memory["id"]}. [{memory["category"]}] {memory["content"]}'
        )

    return "\n".join(lines)

# 長期記憶削除
def delete_memory(memory_ids):
    memories = load_memory()

    deleted = [
        memory for memory in memories
        if memory["id"] in memory_ids
    ]

    if not deleted:
        return "指定された記憶は見つかりませんでした。"

    new_memories = [
        memory for memory in memories
        if memory["id"] not in memory_ids
    ]

    save_memory(new_memories)

    ids = ", ".join(str(memory["id"]) for memory in deleted)
    return f"{ids}番の記憶を削除しました。"

# 長期記憶更新
def update_memory(memory_ids, content, category=None):
    memories = load_memory()

    updated = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for memory in memories:
        if memory["id"] in memory_ids:
            memory["content"] = content
            if category:
                memory["category"] = category
            memory["updated_at"] = now
            updated.append(memory["id"])

    if not updated:
        return "指定された記憶は見つかりませんでした。"

    save_memory(memories)

    ids = ", ".join(str(memory_id) for memory_id in updated)
    return f"{ids}番の記憶を更新しました。"

# 長期記憶意図判定
def load_memory_intent_prompt():
    with open(MEMORY_INTENT_PROMPT_PATH, "r", encoding="utf-8") as file:
        return file.read()


def classify_memory_intent(message: str):
    memory_prompt = load_memory_intent_prompt()

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
    
# 長期記憶判定結果処理
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

# 通常会話に長期記憶を渡す
def format_memory_for_prompt():
    memories = load_memory()

    if not memories:
        return "長期記憶はまだありません。"

    lines = [
        "以下はユーザーに関する長期記憶です。",
        "回答に関係がある場合のみ参考にしてください。"
    ]

    for memory in memories:
        lines.append(
            f'- [{memory["category"]}] {memory["content"]}'
        )

    return "\n".join(lines)

# ルートURLでindex.htmlを返す
@app.get("/")
def read_index():
    return FileResponse("static/index.html")


# フロントエンドから受け取るデータ形式
class ChatRequest(BaseModel):
    message: str


# /chat エンドポイント
@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    def event_generator():
        # 現在日時
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")

        current_datetime_message = {
            "role": "system",
            "content": (
                f"現在日時: {current_time}"
            )
        }
        try:
            note_reply = handle_note_intent(request.message)

            if note_reply is not None:
                yield f"data: {json.dumps({'text': note_reply})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
                return
            
            task_reply = handle_task_intent(request.message)

            if task_reply is not None:
                yield f"data: {json.dumps({'text': task_reply})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
                return
            
            memory_reply = handle_memory_intent(request.message)

            if memory_reply is not None:
                yield f"data: {json.dumps({'text': memory_reply})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
                return
            
            conversation_history.append({
                "role": "user",
                "content": request.message
            })

            trim_history()

            system_prompt = load_system_prompt()

            memory_context = format_memory_for_prompt()

            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                current_datetime_message,
                {
                    "role": "system",
                    "content": memory_context
                }
            ] + conversation_history

            full_reply = ""

            print(messages)
            
            stream = client.responses.create(
                model="gpt-5-mini",
                input=messages,
                stream=True,
                reasoning={"effort": "low"},
            )

            for event in stream:
                if event.type == "response.output_text.delta":
                    text = event.delta
                    full_reply += text

                    yield f"data: {json.dumps({'text': text})}\n\n"

            conversation_history.append({
                "role": "assistant",
                "content": full_reply
            })

            trim_history()

            print(current_time)
            print(conversation_history)

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )