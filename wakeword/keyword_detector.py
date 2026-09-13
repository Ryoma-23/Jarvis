"""Offline, open-vocabulary wake phrases sharing the existing capture stream."""
from pathlib import Path

import numpy as np

from core.config import (
    WAKEWORD_JARVIS_THRESHOLD,
    WAKEWORD_KEYWORD_TRAILING_BLANKS,
)

MODEL_NAME = "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
    + MODEL_NAME + ".tar.bz2"
)
MODEL_FILES = (
    "encoder-epoch-13-avg-2-chunk-8-left-64.int8.onnx",
    "decoder-epoch-13-avg-2-chunk-8-left-64.onnx",
    "joiner-epoch-13-avg-2-chunk-8-left-64.int8.onnx",
    "tokens.txt", "en.phone",
)
PHRASES = ("JARVIS", "WAKE UP", "WAKE UP JARVIS")
PROFILE_VERSION = "jarvis-pronunciation-v3-strict"
# Distinct IDs keep alternative pronunciations separate in the keyword graph.
# Include the final consonant; incomplete names are not accepted.
JARVIS_PRONUNCIATIONS = (
    "j ià b ǐ s", "j iā b ǐ s", "JH AA1 R V IH0 S",
    "JH AA1 B IY0 S", "j iā b èi s", "j ià R IH1 S",
    "JH AE1 B AH0 S",
)
JARVIS_ALIAS_IDS = {f"JARVIS_ALT_{i}" for i in range(len(JARVIS_PRONUNCIATIONS))}
JARVIS_INLINE_KEYWORDS = "/".join(
    f"{phones} :1.0 #{WAKEWORD_JARVIS_THRESHOLD} @JARVIS_ALT_{i}"
    for i, phones in enumerate(JARVIS_PRONUNCIATIONS)
)


def normalize_keyword(result: str) -> str | None:
    if result in JARVIS_ALIAS_IDS:
        return "Jarvis"
    if result in {phrase.replace(" ", "_") for phrase in PHRASES}:
        return result.replace("_", " ").title()
    return None


def prepare_model(directory: Path) -> None:
    """Download official model data only; never extract arbitrary archive paths."""
    import io
    import tarfile
    from urllib.request import urlopen

    directory.mkdir(parents=True, exist_ok=True)
    if not all((directory / name).is_file() for name in MODEL_FILES):
        with urlopen(MODEL_URL, timeout=120) as response:
            archive_bytes = response.read()
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:bz2") as archive:
            for name in MODEL_FILES:
                member = archive.getmember(f"{MODEL_NAME}/{name}")
                if not member.isfile():
                    raise ValueError(f"Not a model file: {name}")
                data = archive.extractfile(member).read()
                (directory / name).write_bytes(data)

    lexicon = {}
    for line in (directory / "en.phone").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts:
            lexicon.setdefault(parts[0].upper(), parts[1:])
    tokens = {line.split()[0] for line in (directory / "tokens.txt").read_text(encoding="utf-8").splitlines() if line.split()}
    lines = []
    for phrase in PHRASES:
        phones = [phone for word in phrase.split() for phone in lexicon[word]]
        if not set(phones) <= tokens:
            raise ValueError(f"Unknown phonemes for {phrase}")
        lines.append(" ".join(phones) + " @" + phrase.replace(" ", "_"))
    (directory / "keywords.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


class KeywordDetector:
    def __init__(self, directory: Path, threshold: float = 0.35):
        for name in (*MODEL_FILES[:4], "keywords.txt"):
            if not (directory / name).is_file():
                raise FileNotFoundError(directory / name)

        tokens = {line.split()[0] for line in
                  (directory / "tokens.txt").read_text(encoding="utf-8").splitlines()
                  if line.split()}
        if not all(set(p.split()) <= tokens for p in JARVIS_PRONUNCIATIONS):
            raise ValueError("Jarvis pronunciation tokens do not match the model")

        import sherpa_onnx

        self._spotter = sherpa_onnx.KeywordSpotter(
            encoder=str(directory / MODEL_FILES[0]),
            decoder=str(directory / MODEL_FILES[1]),
            joiner=str(directory / MODEL_FILES[2]),
            tokens=str(directory / "tokens.txt"),
            keywords_file=str(directory / "keywords.txt"),
            num_threads=1, provider="cpu",
            max_active_paths=16,
            num_trailing_blanks=WAKEWORD_KEYWORD_TRAILING_BLANKS,
            keywords_threshold=threshold,
            keywords_score=1.0,
        )
        self.reset()

    def reset(self) -> None:
        # A fresh stream removes acoustic state across microphone handoffs.
        self._stream = self._spotter.create_stream(JARVIS_INLINE_KEYWORDS)

    def predict(self, audio: np.ndarray) -> str | None:
        self._stream.accept_waveform(16000, audio.astype(np.float32) / 32768.0)
        detected = None
        while self._spotter.is_ready(self._stream):
            self._spotter.decode_stream(self._stream)
            result = self._spotter.get_result(self._stream)
            if result:
                self._spotter.reset_stream(self._stream)
                keyword = normalize_keyword(result)
                if keyword is not None:
                    detected = keyword
        return detected
