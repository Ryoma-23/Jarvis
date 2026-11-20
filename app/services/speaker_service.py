"""Local, observation-only speaker comparison. Never authorizes conversation."""
import hashlib
import io
import json
import math
import shutil
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[2] / "data" / "speaker"
MODEL_NAME = "wespeaker_en_voxceleb_resnet34.onnx"
MODEL_SHA256 = "5ef208a9da1453335308a6b6f4e6dfbd7e183a38b604de0a57664f45d257fe94"
MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/" + MODEL_NAME
MIN_SAMPLES = 8
# Exploratory bands, NOT calibrated identity/security thresholds.
OWNER_THRESHOLD = .60
OTHER_THRESHOLD = .35


class SpeakerError(Exception):
    def __init__(self, code, status=422, quality=None):
        self.code, self.status = code, status
        self.quality = quality


def normalize(vector):
    v = np.asarray(vector, dtype=np.float32)
    if v.ndim != 1 or not np.all(np.isfinite(v)) or np.linalg.norm(v) < 1e-8:
        raise SpeakerError("invalid_embedding")
    return v / np.linalg.norm(v)


def decode_audio(body, enrollment=False):
    try:
        with wave.open(io.BytesIO(body), "rb") as wav:
            rate, channels, width, frames = wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()
            if channels != 1 or width != 2 or rate not in (16000, 24000, 32000, 44100, 48000):
                raise SpeakerError("unsupported_wav")
            if not .2 <= frames / rate <= 16:
                raise SpeakerError("invalid_duration")
            raw = wav.readframes(frames)
            if len(raw) != frames * 2:
                raise SpeakerError("truncated_wav")
    except (wave.Error, EOFError, ValueError):
        raise SpeakerError("invalid_wav") from None
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    clipped = float(np.mean(np.abs(x) >= .995))
    if rate != 16000:
        divisor = math.gcd(rate, 16000)
        x = resample_poly(x, 16000 // divisor, rate // divisor).astype(np.float32)
    # Quality check only: energy cannot distinguish speech from music or another speaker.
    chunks = x[:len(x) // 320 * 320].reshape(-1, 320)
    levels = np.sqrt(np.mean(chunks * chunks, axis=1))
    energetic = np.flatnonzero(levels >= max(.003, float(levels.max(initial=0)) * .10))
    energy_seconds = len(energetic) * .02
    quality = {"duration_s": round(frames / rate, 3), "energy_s": round(energy_seconds, 3),
               "clipped_fraction": round(clipped, 4)}
    if clipped > .03:
        raise SpeakerError("clipped_audio", quality=quality)
    minimum = 2.0 if enrollment else .6
    if energy_seconds < minimum:
        raise SpeakerError("insufficient_audio", quality=quality)
    start = max(0, int(energetic[0]) * 320 - 1600)
    end = min(len(x), (int(energetic[-1]) + 1) * 320 + 1600)
    quality.update(trim_start_s=round(start / 16000, 3), trim_end_s=round(end / 16000, 3))
    return np.ascontiguousarray(x[start:end]), quality


def enrollment_consistency(samples):
    """Descriptive only: similarity is not a calibrated enrollment quality score."""
    vectors = [normalize(s["embedding"]) for s in samples]
    pairs = [float(np.clip(np.dot(a, b), -1, 1))
             for i, a in enumerate(vectors) for b in vectors[i + 1:]]
    return {"pair_count": len(pairs), "pair_min": round(min(pairs), 5) if pairs else None,
            "pair_mean": round(sum(pairs) / len(pairs), 5) if pairs else None}


class SpeakerService:
    def __init__(self, root=ROOT, embedder=None):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.work = threading.Lock()
        self.extractor = None
        self.embedder = embedder

    def path(self, profile):
        name = str(UUID(str(profile)))
        result = (self.root / "profiles" / name).resolve()
        if not result.is_relative_to((self.root / "profiles").resolve()):
            raise SpeakerError("invalid_profile")
        return result

    def read(self, profile):
        try:
            return json.loads((self.path(profile) / "profile.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SpeakerError("profile_not_found", 404) from None

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    def status(self):
        with self.lock:
            profiles = []
            for p in (self.root / "profiles").glob("*/profile.json"):
                d = json.loads(p.read_text(encoding="utf-8"))
                profiles.append({"id": d["id"], "created_at": d["created_at"],
                                 "samples": len(d["samples"]), "prompts": [s["prompt"] for s in d["samples"]],
                                 "consistency": enrollment_consistency(d["samples"])})
            active = None
            if (self.root / "active.json").exists():
                active = json.loads((self.root / "active.json").read_text())["id"]
            return {"model_available": (self.root / "models" / MODEL_NAME).exists(),
                    "active": active, "profiles": sorted(profiles, key=lambda p: p["created_at"]),
                    "minimum_samples": MIN_SAMPLES, "owner_threshold": OWNER_THRESHOLD,
                    "other_threshold": OTHER_THRESHOLD, "calibrated": False}

    def create(self):
        with self.lock:
            profile = {"id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
                       "model_sha256": MODEL_SHA256, "samples": []}
            self.write(self.path(profile["id"]) / "profile.json", profile)
            return {"id": profile["id"]}

    def prepare(self):
        if self.embedder or self.extractor:
            return
        path = self.root / "models" / MODEL_NAME
        if not path.exists():
            raise SpeakerError("model_missing", 503)
        if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
            raise SpeakerError("model_checksum_mismatch", 503)
        import sherpa_onnx
        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(path), num_threads=1, provider="cpu")
        if not config.validate():
            raise SpeakerError("invalid_model", 503)
        self.extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)

    def embedding(self, audio):
        self.prepare()
        if self.embedder:
            return normalize(self.embedder(audio))
        stream = self.extractor.create_stream()
        stream.accept_waveform(sample_rate=16000, waveform=audio)
        stream.input_finished()
        if not self.extractor.is_ready(stream):
            raise SpeakerError("insufficient_audio")
        return normalize(self.extractor.compute(stream))

    def enroll(self, profile, prompt, body):
        if not self.work.acquire(blocking=False):
            raise SpeakerError("busy", 429)
        try:
            audio, quality = decode_audio(body, enrollment=True)
            vector = self.embedding(audio)
            with self.lock:
                d = self.read(profile)
                if prompt in [s["prompt"] for s in d["samples"]]:
                    raise SpeakerError("prompt_already_recorded", 409)
                sample = str(uuid4())
                # Only explicitly enrolled clips are persisted. Shadow clips never reach this path.
                (self.path(profile) / (sample + ".wav")).write_bytes(body)
                d["samples"].append({"id": sample, "prompt": prompt, "embedding": vector.tolist(), "quality": quality})
                self.write(self.path(profile) / "profile.json", d)
                return {"samples": len(d["samples"]), "quality": quality}
        finally:
            self.work.release()

    def activate(self, profile):
        with self.lock:
            d = self.read(profile)
            if len(d["samples"]) < MIN_SAMPLES:
                raise SpeakerError("more_samples_required")
            self.write(self.root / "active.json", {"id": d["id"]})
            return {"active": d["id"]}

    def delete(self, profile):
        with self.lock:
            d = self.read(profile)
            active_file = self.root / "active.json"
            if active_file.exists() and json.loads(active_file.read_text())["id"] == d["id"]:
                active_file.unlink()
            shutil.rmtree(self.path(profile))  # UUID-only path checked by path(); explicit UI deletion.
            return {"deleted": d["id"]}

    def compare(self, body):
        if not self.work.acquire(blocking=False):
            raise SpeakerError("busy", 429)
        started = time.perf_counter()
        try:
            with self.lock:
                active = self.status()["active"]
                if not active:
                    raise SpeakerError("not_enrolled", 409)
                profile = self.read(active)
            if profile["model_sha256"] != MODEL_SHA256:
                raise SpeakerError("profile_model_mismatch", 409)
            quality = None
            try:
                audio, quality = decode_audio(body)
                vector = self.embedding(audio)
            except SpeakerError as error:
                if error.code in {"insufficient_audio", "clipped_audio"}:
                    return {"decision": "insufficient", "reason": error.code, "score": None,
                            "quality": error.quality or quality,
                            "compute_ms": round((time.perf_counter() - started) * 1000, 1), "profile": active}
                raise
            reference = normalize(np.mean([s["embedding"] for s in profile["samples"]], axis=0))
            score = float(np.clip(np.dot(vector, reference), -1, 1))
            return {"decision": "owner_candidate" if score >= OWNER_THRESHOLD else
                    "other_candidate" if score < OTHER_THRESHOLD else "uncertain",
                    "score": round(score, 5), "compute_ms": round((time.perf_counter() - started) * 1000, 1),
                    "quality": quality, "profile": active, "calibrated": False,
                    "owner_threshold": OWNER_THRESHOLD, "other_threshold": OTHER_THRESHOLD}
        finally:
            self.work.release()


service = SpeakerService()
