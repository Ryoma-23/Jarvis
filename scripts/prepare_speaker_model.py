"""Download the pinned public model only; never reads microphone/user audio."""
import hashlib
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.speaker_service import ROOT, MODEL_NAME, MODEL_URL, MODEL_SHA256


def main():
    target = ROOT / "models" / MODEL_NAME
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == MODEL_SHA256:
        print("Speaker model already verified.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".download")
    with requests.get(MODEL_URL, stream=True, timeout=(15, 120)) as response:
        response.raise_for_status()
        digest = hashlib.sha256()
        size = 0
        with temporary.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                size += len(chunk)
                if size > 40_000_000:
                    raise RuntimeError("Model download exceeds expected size")
                output.write(chunk)
                digest.update(chunk)
    if digest.hexdigest() != MODEL_SHA256:
        raise RuntimeError("Model checksum mismatch; not installed")
    temporary.replace(target)
    print(f"Verified model installed: {target} ({size} bytes)")


if __name__ == "__main__":
    main()
