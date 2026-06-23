from fastapi import APIRouter
from app.services.realtime_service import create_realtime_token

router = APIRouter()


@router.get("/realtime/token")
def get_realtime_token():
    return create_realtime_token()