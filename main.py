from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routes.chat import router as chat_router
from app.routes.realtime import router as realtime_router


# FastAPIアプリを作成
app = FastAPI()


@app.middleware("http")
async def revalidate_local_ui_assets(request, call_next):
    response = await call_next(request)

    if (
        request.url.path == "/"
        or request.url.path.startswith("/static/")
    ):
        response.headers["Cache-Control"] = "no-cache"

    return response


# staticフォルダを配信対象にする
app.mount("/static", StaticFiles(directory="static"), name="static")


app.include_router(chat_router)
app.include_router(realtime_router)

