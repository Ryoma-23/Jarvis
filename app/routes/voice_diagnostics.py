"""Opt-in local diagnostics. Never accepts audio or arbitrary event payloads."""
import json
import math
import threading
from collections import Counter
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

router = APIRouter(prefix="/voice-diagnostics")
SAVE_DIR = Path(__file__).resolve().parents[2] / "data" / "voice_diagnostics"
_lock = threading.Lock()


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    ms: float = Field(ge=0, le=86400000)
    kind: Literal["start", "stop", "connection_start", "connection_end", "microphone",
                  "ready", "speech_start", "speech_stop", "transcript", "transcription_failed",
                  "accepted", "rejected", "response_request", "response_created", "audio_start",
                  "response_done", "error", "trial", "mark", "speaker_result", "speaker_label"]
    session: str = Field(default="", max_length=128)
    item: str = Field(default="", max_length=128)
    response: str = Field(default="", max_length=128)
    trial: int = Field(default=0, ge=0, le=1000)
    scenario: Literal["quiet", "video_only", "video_and_me", "interrupt"] = "quiet"
    value: str = Field(default="", max_length=200)
    chars: int = Field(default=0, ge=0, le=100000)
    transcript: str | None = Field(default=None, max_length=2000)
    device: str | None = Field(default=None, max_length=256)
    sample_rate: int | None = Field(default=None, ge=0, le=384000)
    channels: int | None = Field(default=None, ge=0, le=64)
    muted: bool | None = None
    enabled: bool | None = None
    echo_cancellation: bool | None = None
    noise_suppression: bool | None = None
    auto_gain: bool | None = None
    score: float | None = Field(default=None, ge=-1, le=1)
    compute_ms: float | None = Field(default=None, ge=0, le=120000)
    roundtrip_ms: float | None = Field(default=None, ge=0, le=120000)
    profile: str | None = Field(default=None, max_length=36)
    owner_threshold: float | None = Field(default=None, ge=-1, le=1)
    other_threshold: float | None = Field(default=None, ge=-1, le=1)
    error_code: str | None = Field(default=None, max_length=80)
    response_active: bool | None = None
    pending_requests: int | None = Field(default=None, ge=0, le=10000)
    overlap_output: bool | None = None
    audio_duration_s: float | None = Field(default=None, ge=0, le=16)
    energy_s: float | None = Field(default=None, ge=0, le=16)
    speaker_label: Literal["owner", "video", "mixed", "unknown"] | None = None
    reason: str | None = Field(default=None, max_length=80)
    clipped_fraction: float | None = Field(default=None, ge=0, le=1)
    trim_start_s: float | None = Field(default=None, ge=0, le=16)
    trim_end_s: float | None = Field(default=None, ge=0, le=16)
    capture_start_sample: int | None = Field(default=None, ge=0)
    capture_end_sample: int | None = Field(default=None, ge=0)
    capture_rate: int | None = Field(default=None, ge=8000, le=384000)
    capture_start_received_ms: float | None = Field(default=None, ge=0)
    capture_stop_received_ms: float | None = Field(default=None, ge=0)
    server_audio_start_ms: float | None = Field(default=None, ge=0)
    server_audio_end_ms: float | None = Field(default=None, ge=0)


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    started_at: str = Field(max_length=40)
    include_transcript: bool = False
    complete: bool = False
    events: list[Event] = Field(max_length=10000)

    @model_validator(mode="after")
    def validate_events(self):
        if any(b.ms < a.ms for a, b in zip(self.events, self.events[1:])):
            raise ValueError("Events must be ordered")
        if not self.include_transcript:
            for event in self.events:
                event.transcript = None
        known = set()
        for event in self.events:
            if event.kind == "speech_start" and event.item:
                known.add((event.session, event.item))
            if event.kind == "speaker_label" and (
                (event.session, event.item) not in known or event.speaker_label is None
            ):
                raise ValueError("Speaker labels require an observed turn and valid label")
        return self


def summarize(snapshot):
    counts = Counter(e.kind for e in snapshot.events)
    turns, trials = {}, {}
    pending, response_links = {}, {}
    for e in snapshot.events:
        if e.kind == "trial":
            trials[e.trial] = {"number": e.trial, "scenario": e.scenario, "started_ms": e.ms, "marks": []}
        if e.kind == "mark" and e.trial in trials:
            trials[e.trial]["marks"].append(e.value)
        key = (e.session, e.item)
        if e.item and e.kind in {"speech_start", "speech_stop", "transcript", "accepted", "rejected", "transcription_failed", "response_request"}:
            turn = turns.setdefault(key, {"session": e.session, "item": e.item, "trial": e.trial})
            turn.setdefault(e.kind + "_ms", e.ms)
            if e.kind == "rejected":
                turn["rejection_reason"] = e.value
        if e.kind == "response_request":
            pending.setdefault(e.session, []).append(e)
        if e.kind == "response_created":
            queue = pending.pop(e.session, [])
            # No server request ID echo: only a single outstanding request can be inferred.
            if len(queue) == 1 and queue[0].item:
                response_links[(e.session, e.response)] = (e.session, queue[0].item)
        if e.kind in {"error", "connection_end"}:
            pending.pop(e.session, None)
        if e.kind == "audio_start":
            linked = response_links.pop((e.session, e.response), None)
            if linked in turns:
                turns[linked].setdefault("audio_start_ms", e.ms)
                turns[linked]["response_link"] = "inferred_single_pending_request"
    metrics = {}
    for name, start, end in [
        ("stop_to_transcript", "speech_stop", "transcript"),
        ("stop_to_request", "speech_stop", "response_request"),
        ("transcript_to_request", "transcript", "response_request"),
        ("request_to_audio", "response_request", "audio_start"),
        ("stop_to_audio", "speech_stop", "audio_start"),
    ]:
        values = sorted(t[end + "_ms"] - t[start + "_ms"] for t in turns.values()
                        if start + "_ms" in t and end + "_ms" in t)
        metrics[name] = {"count": len(values), "mean_ms": round(sum(values) / len(values), 1) if values else None,
                         "p95_ms": round(values[math.ceil(.95 * len(values)) - 1], 1) if values else None}
    manual = {}
    for scenario in ("quiet", "video_only", "video_and_me", "interrupt"):
        selected = [t for t in trials.values() if t["scenario"] == scenario]
        heard = sum("heard" in t["marks"] and "missed" not in t["marks"] and "unknown" not in t["marks"] for t in selected)
        missed = sum("missed" in t["marks"] and "heard" not in t["marks"] and "unknown" not in t["marks"] for t in selected)
        manual[scenario] = {"trials": len(selected), "heard": heard, "missed": missed,
                            "unknown_or_conflicting": len(selected) - heard - missed,
                            "false_response_marks": sum(t["marks"].count("false_response") for t in selected),
                            "reported_success_rate": heard / (heard + missed) if heard + missed and scenario != "video_only" else None}
    comparisons = [e.model_dump(exclude_none=True) for e in snapshot.events if e.kind == "speaker_result"]
    labels = {(e.session, e.item): e.speaker_label for e in snapshot.events if e.kind == "speaker_label"}
    for turn in turns.values():
        turn["speaker_label"] = labels.get((turn["session"], turn["item"]), "unknown")
    for result in comparisons:
        result["speaker_label"] = labels.get((result["session"], result["item"]), "unknown")
    return {"counts": dict(counts), "manual_by_scenario": manual, "metrics": metrics, "turns": list(turns.values()),
            "speaker_observations": {"counts": dict(Counter(e["value"] for e in comparisons)),
                                     "calibrated": False, "results": comparisons},
            "trials": list(trials.values()),
            "notes": ["Times are browser receipt times, not physical sound timestamps.",
                      "Negative transcript_to_request means response requested before transcription.",
                      "Response links are inferred only for a single outstanding request; ambiguous links are omitted.",
                      "Marks are manual observations, not automatic speaker ground truth. Unmarked trials are unknown."]}


def save_snapshot(snapshot):
    document = snapshot.model_dump(mode="json")
    document["report"] = summarize(snapshot)
    name = str(snapshot.id) + ".json"
    with _lock:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        target = SAVE_DIR / name
        if target.exists():
            previous = json.loads(target.read_text(encoding="utf-8"))
            if previous == document:
                return {"file": "data/voice_diagnostics/" + name, "report": document["report"]}
            if previous["complete"] or len(previous["events"]) > len(snapshot.events):
                raise HTTPException(409, "Snapshot already completed or newer")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    return {"file": "data/voice_diagnostics/" + name, "report": document["report"]}


@router.post("")
async def save_diagnostics(request: Request):
    # Same-origin browser API; reject cross-site submissions and bounded body size.
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Origin mismatch")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4_000_000:
            raise HTTPException(413, "Diagnostic snapshot too large")
    try:
        snapshot = Snapshot.model_validate_json(bytes(body))
    except ValidationError:
        raise HTTPException(422, "Invalid diagnostic snapshot") from None
    try:
        return save_snapshot(snapshot)
    except OSError:
        raise HTTPException(503, "Diagnostic save failed") from None
