from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.services.speaker_service import SpeakerError, service

router = APIRouter(prefix="/speaker")


async def invoke(request, function, *args):
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "origin_mismatch")
    try:
        return await run_in_threadpool(function, *args)
    except SpeakerError as error:
        raise HTTPException(error.status, error.code) from None
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(503, "speaker_processing_failed") from None


async def audio_body(request):
    if request.headers.get("content-type", "").split(";")[0] != "audio/wav":
        raise HTTPException(415, "audio_wav_required")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 1_600_000:
            raise HTTPException(413, "audio_too_large")
    return bytes(data)


@router.get("/status")
async def status(request: Request):
    return await invoke(request, service.status)


@router.post("/profiles")
async def create(request: Request):
    return await invoke(request, service.create)


@router.post("/profiles/{profile}/samples/{prompt}")
async def enroll(request: Request, profile: UUID, prompt: int):
    if not 0 <= prompt < 10:
        raise HTTPException(422, "invalid_prompt")
    return await invoke(request, service.enroll, str(profile), prompt, await audio_body(request))


@router.post("/profiles/{profile}/activate")
async def activate(request: Request, profile: UUID):
    return await invoke(request, service.activate, str(profile))


@router.delete("/profiles/{profile}")
async def delete(request: Request, profile: UUID):
    return await invoke(request, service.delete, str(profile))


@router.post("/compare")
async def compare(request: Request):
    return await invoke(request, service.compare, await audio_body(request))
