from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.services.chat_service import generate_chat_stream


router = APIRouter()


class ChatRequest(BaseModel):
    message: str


@router.get("/")
def read_index():
    return FileResponse("static/index.html")


@router.post("/chat/stream")
def chat_stream(request: ChatRequest):
    return StreamingResponse(
        generate_chat_stream(request.message),
        media_type="text/event-stream"
    )