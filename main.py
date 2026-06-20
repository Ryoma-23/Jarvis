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

SYSTEM_PROMPT_PATH = BASE_DIR / "prompts" / "system_prompt.txt"

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
    prompt = f"""
あなたはメモ操作の意図判定AIです。
ユーザー入力がメモ操作かどうかを判定してください。

必ずJSONだけを返してください。説明文は禁止です。

actionは次のいずれかです。
- none
- add
- list
- search
- delete

ルール:
- メモを残す、メモして、覚え書き、記録して、控えておいて → add
- メモ一覧、メモ見せて、保存したメモ → list
- 〇〇のメモある？、〇〇のメモ探して → search
- 〇番のメモを消して、削除して → delete
- メモ操作でなければ none

削除ルール:
- 「3番のメモを削除」→ note_ids: [3], delete_all: false
- 「3.4.5のメモ削除」「3,4,5番を削除」→ note_ids: [3,4,5], delete_all: false
- 「すべてのメモを削除」「全部消して」「全削除」→ note_ids: [], delete_all: true

出力形式:
{{
  "action": "add | list | search | delete | none",
  "content": "追加するメモ本文。なければ null",
  "keyword": "検索キーワード。なければ null",
  "note_ids": [削除するメモIDの配列。なければ []],
  "note_id": 削除するメモID。なければ null
}}

ユーザー入力:
{message}
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt,
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
        try:
            note_reply = handle_note_intent(request.message)

            if note_reply is not None:
                yield f"data: {json.dumps({'text': note_reply})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
                return

            conversation_history.append({
                "role": "user",
                "content": request.message
            })

            trim_history()

            system_prompt = load_system_prompt()

            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                }
            ] + conversation_history

            full_reply = ""
            
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

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )