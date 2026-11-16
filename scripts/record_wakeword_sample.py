"""Record one local evaluation WAV using the live wake-word microphone settings."""
import argparse
import math
from pathlib import Path
import shutil
import sys
import tempfile
import time
import wave

import numpy as np
import sounddevice as sd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import (
    WAKEWORD_CAPTURE_CHANNELS, WAKEWORD_DTYPE, WAKEWORD_MIC_CHANNEL_INDEX,
)
from wakeword.audio_device import find_wakeword_input_device


def validate_request(output, seconds):
    if not math.isfinite(seconds) or not 0 < seconds <= 600:
        raise ValueError("Recording duration must be greater than 0 and at most 600 seconds")
    if output.suffix.lower() != ".wav":
        raise ValueError("Output must have a .wav extension")
    if output.exists():
        raise FileExistsError("Output already exists; choose a new filename")


def record_sample(output, seconds, device):
    """Capture in bounded blocks, publishing a WAV only after successful capture."""
    validate_request(output, seconds)
    rate = device.default_sample_rate
    total_frames = int(round(rate * seconds))
    block_size = int(rate * 0.08)
    if total_frames < 1 or block_size < 1:
        raise ValueError("Invalid recording length or microphone sample rate")
    if device.input_channels < WAKEWORD_CAPTURE_CHANNELS:
        raise ValueError("Microphone has fewer channels than the live wake-word configuration")
    if not 0 <= WAKEWORD_MIC_CHANNEL_INDEX < WAKEWORD_CAPTURE_CHANNELS:
        raise ValueError("Invalid configured microphone channel")

    peak = 0
    square_sum = 0.0
    clipped = 0
    remaining = total_frames
    with tempfile.TemporaryFile(mode="w+b") as temporary:
        with wave.open(temporary, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(rate)
            with sd.InputStream(
                device=device.index, samplerate=rate, blocksize=block_size,
                channels=WAKEWORD_CAPTURE_CHANNELS, dtype=WAKEWORD_DTYPE,
            ) as stream:
                while remaining:
                    count = min(block_size, remaining)
                    audio, overflowed = stream.read(count)
                    if overflowed:
                        raise RuntimeError("Microphone input overflowed; sample was not saved")
                    if audio.shape != (count, WAKEWORD_CAPTURE_CHANNELS):
                        raise RuntimeError("Unexpected microphone frame shape; sample was not saved")
                    mono = audio[:, WAKEWORD_MIC_CHANNEL_INDEX].astype("<i2")
                    values = mono.astype(np.float64)
                    peak = max(peak, int(np.max(np.abs(values))))
                    square_sum += float(np.dot(values, values))
                    clipped += int(np.count_nonzero((mono == -32768) | (mono == 32767)))
                    target.writeframesraw(mono.tobytes())
                    remaining -= count
        if peak == 0:
            raise RuntimeError("Microphone returned only digital zeros; sample was not saved")
        temporary.seek(0)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also protects against a file created during recording.
        with output.open("xb") as destination:
            shutil.copyfileobj(temporary, destination)
    return {
        "frames": total_frames, "sample_rate": rate,
        "duration_seconds": total_frames / rate,
        "peak": peak, "rms": math.sqrt(square_sum / total_frames),
        "clipped_samples": clipped,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New WAV filename (never overwritten)")
    parser.add_argument("--seconds", type=float, default=5, help="Duration, 0 < seconds <= 600 (default: 5)")
    parser.add_argument("--countdown", type=int, default=3, choices=range(0, 11),
                        help="Seconds before opening the microphone (default: 3)")
    args = parser.parse_args(argv)
    try:
        validate_request(args.output, args.seconds)
        device = find_wakeword_input_device()
        print("Close the JARVIS Tray before recording to release the microphone.", flush=True)
        print(f"Microphone: {device.name} / {device.host_api_name}; "
              f"{device.default_sample_rate} Hz; source channel {WAKEWORD_MIC_CHANNEL_INDEX}", flush=True)
        print(f"Local recording: {args.seconds:g} seconds -> {args.output}", flush=True)
        for remaining in range(args.countdown, 0, -1):
            print(f"Starting in {remaining}...", flush=True)
            time.sleep(1)
        print("RECORDING. For a positive clip, leave a short silence then say the wake phrase once.", flush=True)
        result = record_sample(args.output, args.seconds, device)
        print(f"Saved: {args.output} ({result['duration_seconds']:.3f}s, mono PCM16)")
        print(f"Peak={result['peak']} RMS={result['rms']:.2f} clipped_samples={result['clipped_samples']}")
        if result["clipped_samples"]:
            print("Clipping detected. Consider recording another sample at a lower microphone gain.")
        if result["peak"] < 100:
            print("Very low input level. Check microphone placement and gain before evaluation.")
        return 0
    except KeyboardInterrupt:
        print("Recording interrupted. Capture-stage interruptions do not save a WAV.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Recording failed ({type(error).__name__}): {error}", file=sys.stderr)
        print("If final file writing failed, a partial output may remain; use a new filename.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
