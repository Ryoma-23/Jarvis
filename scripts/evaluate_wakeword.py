"""Evaluate local PCM16 WAV files without microphone access or app activation."""
import argparse
import json
import math
from pathlib import Path
import sys
import wave

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import (
    WAKEWORD_COOLDOWN_SECONDS, WAKEWORD_JARVIS_THRESHOLD,
    WAKEWORD_KEYWORD_MODEL_DIR, WAKEWORD_KEYWORD_THRESHOLD,
    WAKEWORD_KEYWORD_TRAILING_BLANKS, WAKEWORD_MODEL_NAME,
    WAKEWORD_TARGET_FRAME_SAMPLES, WAKEWORD_TARGET_SAMPLE_RATE,
    WAKEWORD_THRESHOLD,
)
from wakeword.audio_converter import convert_sample_rate
from wakeword.keyword_detector import (
    JARVIS_ALIAS_IDS, JARVIS_BASE_PRONUNCIATION, JARVIS_PRONUNCIATIONS,
    KeywordDetector, PROFILE_VERSION,
)

FRAME_SECONDS = WAKEWORD_TARGET_FRAME_SAMPLES / WAKEWORD_TARGET_SAMPLE_RATE
# Flush streaming-model latency, without cutting off words near the end of a clip.
TAIL_FRAMES = math.ceil(1.0 / FRAME_SECONDS)


def validate_wav(source, channel):
    if source.getsampwidth() != 2 or source.getcomptype() != "NONE":
        raise ValueError("Only uncompressed 16-bit PCM WAV is supported")
    if channel < 0 or channel >= source.getnchannels():
        raise ValueError(f"Channel {channel} is not present in this WAV")
    if source.getnframes() == 0:
        raise ValueError("WAV contains no audio")
    # Match the live listener's 80 ms capture blocks exactly.
    block_size = int(source.getframerate() * FRAME_SECONDS)
    if block_size < 1:
        raise ValueError("Unsupported WAV sample rate")
    return block_size


def audio_frames(source, channel, block_size):
    remaining = source.getnframes()
    while remaining:
        count = min(block_size, remaining)
        raw = source.readframes(count)
        if len(raw) != count * source.getnchannels() * 2:
            raise ValueError("WAV audio data is truncated")
        samples = np.frombuffer(raw, dtype="<i2").reshape(-1, source.getnchannels())[:, channel]
        samples = np.pad(samples, (0, block_size - len(samples)))
        frame = convert_sample_rate(samples, source.getframerate(), WAKEWORD_TARGET_SAMPLE_RATE)
        if len(frame) != WAKEWORD_TARGET_FRAME_SAMPLES:
            raise ValueError("WAV sample rate does not produce 80 ms model frames")
        yield frame
        remaining -= count
    for _ in range(TAIL_FRAMES):
        yield np.zeros(WAKEWORD_TARGET_FRAME_SAMPLES, dtype=np.int16)


def evaluate_file(path, label, channel, model, detector, *, openwakeword_threshold=WAKEWORD_THRESHOLD):
    """Independent continuous-listening trial; cooldown groups repeated hits."""
    model.reset()
    detector.reset()
    events = []
    peak_score = 0.0
    last_event_time = -math.inf
    with wave.open(str(path), "rb") as source:
        block_size = validate_wav(source, channel)
        duration = source.getnframes() / source.getframerate()
        sample_rate = source.getframerate()
        channels = source.getnchannels()
        expected_name = WAKEWORD_MODEL_NAME.lower().replace("-", "_").replace(" ", "_")
        model_name = None
        for index, frame in enumerate(audio_frames(source, channel, block_size)):
            predictions = model.predict(frame)
            if model_name is None:
                # Match the listener, including installed version-suffixed names.
                for name in predictions:
                    normalized = name.lower().replace("-", "_").replace(" ", "_")
                    if normalized == expected_name or "jarvis" in normalized:
                        model_name = name
                        break
            if model_name not in predictions:
                raise ValueError(f"Missing openWakeWord prediction: {expected_name}")
            score = float(predictions[model_name])
            if not math.isfinite(score):
                raise ValueError("Non-finite openWakeWord score")
            peak_score = max(peak_score, score)
            keyword = detector.predict(frame)
            time_seconds = (index + 1) * FRAME_SECONDS
            if keyword is None and score < openwakeword_threshold:
                continue
            if time_seconds - last_event_time + 1e-9 < WAKEWORD_COOLDOWN_SECONDS:
                continue
            last_event_time = time_seconds
            keyword_id = detector.last_detection_id if keyword else None
            pronunciation = None
            threshold = None
            if keyword_id in JARVIS_ALIAS_IDS:
                pronunciation = JARVIS_PRONUNCIATIONS[int(keyword_id.rsplit("_", 1)[1])]
                threshold = detector.jarvis_threshold
            elif keyword_id == "JARVIS":
                pronunciation = JARVIS_BASE_PRONUNCIATION
                threshold = detector.threshold
            detectors = []
            if score >= openwakeword_threshold:
                detectors.append("openwakeword")
            if keyword:
                detectors.append("sherpa_onnx")
            events.append({
                "time_seconds": round(time_seconds, 4),
                "during_padding": time_seconds > duration,
                "detectors": detectors,
                "keyword": keyword or "Hey Jarvis",
                "openwakeword_model": model_name,
                "openwakeword_score": score,
                "sherpa_keyword_id": keyword_id,
                "sherpa_pronunciation": pronunciation,
                "sherpa_threshold": threshold,
                "sherpa_score": None,
            })
    return {
        "file": str(path), "label": label, "duration_seconds": duration,
        "sample_rate": sample_rate, "channels": channels, "channel": channel,
        "detected": bool(events), "event_count": len(events),
        "openwakeword_model": model_name,
        "peak_openwakeword_score": peak_score, "events": events,
    }


def summarize(results):
    positive = [item for item in results if item["label"] == "positive"]
    negative = [item for item in results if item["label"] == "negative"]
    hits = sum(item["detected"] for item in positive)
    negative_seconds = sum(item["duration_seconds"] for item in negative)
    false_events = sum(item["event_count"] for item in negative)
    return {
        "positive_clips": len(positive), "positive_clips_detected": hits,
        "positive_clips_missed": len(positive) - hits,
        "positive_clip_detection_rate": hits / len(positive) if positive else None,
        "negative_clips": len(negative),
        "negative_clips_with_detections": sum(item["detected"] for item in negative),
        "negative_duration_seconds": negative_seconds,
        "negative_events": false_events,
        "negative_events_per_hour": false_events * 3600 / negative_seconds if negative_seconds else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive", type=Path, action="append", default=[],
                        help="WAV containing one deliberate Jarvis/Hey Jarvis call; repeatable")
    parser.add_argument("--negative", type=Path, action="append", default=[],
                        help="WAV with no intended call (background/video); repeatable")
    parser.add_argument("--channel", type=int, default=0, help="Zero-based WAV channel (default: 0)")
    parser.add_argument("--output", type=Path, help="New JSON report file; existing files are not overwritten")
    parser.add_argument("--openwakeword-threshold", type=float, default=WAKEWORD_THRESHOLD)
    parser.add_argument("--sherpa-threshold", type=float, default=WAKEWORD_KEYWORD_THRESHOLD,
                        help="Threshold for the base JARVIS pronunciation")
    parser.add_argument("--jarvis-threshold", type=float, default=WAKEWORD_JARVIS_THRESHOLD,
                        help="Threshold for all seven alternate Jarvis pronunciations")
    parser.add_argument("--trailing-blanks", type=int, default=WAKEWORD_KEYWORD_TRAILING_BLANKS)
    args = parser.parse_args(argv)
    for value in (args.openwakeword_threshold, args.sherpa_threshold, args.jarvis_threshold):
        if not math.isfinite(value) or not 0 <= value <= 1:
            parser.error("Thresholds must be finite values between 0 and 1")
    if args.trailing_blanks < 1:
        parser.error("--trailing-blanks must be a positive integer")
    cases = [(path.resolve(), label) for label in ("positive", "negative")
             for path in getattr(args, label)]
    if not cases:
        parser.error("Provide at least one --positive or --negative WAV")
    if len({path for path, _ in cases}) != len(cases):
        parser.error("Each WAV must be listed once, with one label")
    try:
        if args.output and args.output.exists():
            raise FileExistsError("Report already exists; choose a new --output path")
        for path, _ in cases:
            with wave.open(str(path), "rb") as source:
                validate_wav(source, args.channel)
        # Load installed models only. Never download models or fall back silently.
        from openwakeword.model import Model
        model = Model(wakeword_models=[WAKEWORD_MODEL_NAME], inference_framework="onnx")
        detector = KeywordDetector(
            WAKEWORD_KEYWORD_MODEL_DIR, args.sherpa_threshold,
            jarvis_threshold=args.jarvis_threshold, trailing_blanks=args.trailing_blanks,
        )
        results = []
        for path, label in cases:
            print(f"Evaluating {label}: {path.name}", file=sys.stderr)
            results.append(evaluate_file(
                path, label, args.channel, model, detector,
                openwakeword_threshold=args.openwakeword_threshold,
            ))
        report = {
            "schema_version": 1, "profile": PROFILE_VERSION,
            "settings": {
                "openwakeword_threshold": args.openwakeword_threshold,
                "sherpa_base_threshold": args.sherpa_threshold,
                "sherpa_alias_threshold": args.jarvis_threshold,
                "sherpa_trailing_blanks": args.trailing_blanks,
                "frame_seconds": FRAME_SECONDS,
                "tail_padding_seconds": TAIL_FRAMES * FRAME_SECONDS,
                "cooldown_seconds": WAKEWORD_COOLDOWN_SECONDS,
                "startup_guard_applied": False,
                "conversation_lifecycle_simulated": False,
            },
            "summary": summarize(results), "files": results,
        }
        serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            with args.output.open("x", encoding="utf-8") as target:
                target.write(serialized + "\n")
            print(f"Report: {args.output}", file=sys.stderr)
        else:
            print(serialized)
        return 0
    except Exception as error:
        print(f"Evaluation failed ({type(error).__name__}): {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
