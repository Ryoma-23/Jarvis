import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from app.config import (
    DATA_DIR,
    NOTES_FILE,
    TASKS_FILE,
    MEMORY_FILE,
    SYSTEM_PROMPT_PATH,
    NOTE_INTENT_PROMPT_PATH,
    TASK_INTENT_PROMPT_PATH,
    MEMORY_INTENT_PROMPT_PATH
)
from app.openai_client import client
from app.services.note_service import (
    add_note,
    format_notes_list,
    search_notes,
    delete_note,
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
    update_memory,
    format_memory_for_prompt
)
from app.services.intent_service import (
    handle_note_intent,
    handle_task_intent,
    handle_memory_intent
)


# 会話履歴用リストを作成
conversation_history = []

# 履歴件数制限
MAX_HISTORY = 30

# 全件削除確認フラグ
pending_delete_all = False

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