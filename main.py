from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routes.chat import router as chat_router
from app.routes.realtime import router as realtime_router


# FastAPIアプリを作成
app = FastAPI()


# staticフォルダを配信対象にする
app.mount("/static", StaticFiles(directory="static"), name="static")


app.include_router(chat_router)
app.include_router(realtime_router)

