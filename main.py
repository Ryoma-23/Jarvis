import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel


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

# FastAPIアプリを作成
app = FastAPI()

# staticフォルダを配信対象にする
app.mount("/static", StaticFiles(directory="static"), name="static")

def trim_history():
    global conversation_history

    if len(conversation_history) > MAX_HISTORY:
        conversation_history = conversation_history[-MAX_HISTORY:]


# ルートURLでindex.htmlを返す
@app.get("/")
def read_index():
    return FileResponse("static/index.html")


# フロントエンドから受け取るデータ形式
class ChatRequest(BaseModel):
    message: str


# /chat エンドポイント
@app.post("/chat")
def chat(request: ChatRequest):
    try:
        #ユーザーの発言を履歴に追加
        conversation_history.append({
            "role": "user",
            "content": request.message
        })

        trim_history()

        # 会話履歴ごとOpenAIへ送信
        response = client.responses.create(
            model="gpt-5",
            input=conversation_history
        )

        # AIの回答を取得
        reply = response.output_text

        # AIの回答を履歴に追加
        conversation_history.append({
            "role": "assistant",
            "content": reply
        })

        trim_history()

        return {
            "reply": reply
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"OpenAI API呼び出し中にエラーが発生しました: {str(e)}"
        )