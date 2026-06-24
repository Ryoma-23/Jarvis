from fastapi import APIRouter
from app.services.realtime_service import create_realtime_token
from pydantic import BaseModel
from app.services.realtime_tool_service import execute_realtime_tool

router = APIRouter()

class RealtimeToolRequest(BaseModel):
    tool_name: str
    arguments: dict


@router.get("/realtime/token")
def get_realtime_token():
    return create_realtime_token()

@router.post("/realtime/tools")
def execute_tool(request: RealtimeToolRequest):
    return execute_realtime_tool(request.tool_name, request.arguments)