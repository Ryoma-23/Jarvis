"""Offline, open-vocabulary wake phrases sharing the existing capture stream."""
from pathlib import Path
from tempfile import TemporaryDirectory
import math

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
PHRASES = ("JARVIS",)
PROFILE_VERSION = "jarvis-pronunciation-v4-name-only"
JARVIS_BASE_PRONUNCIATION = "JH AA1 R V AH0 S"
# Distinct IDs keep alternative pronunciations separate in the keyword graph.
# Include the final consonant; incomplete names are not accepted.
JARVIS_PRONUNCIATIONS = (
    "j ià b ǐ s", "j iā b ǐ s", "JH AA1 R V IH0 S",
    "JH AA1 B IY0 S", "j iā b èi s", "j ià R IH1 S",
    "JH AE1 B AH0 S",
)
JARVIS_ALIAS_IDS = {f"JARVIS_ALT_{i}" for i in range(len(JARVIS_PRONUNCIATIONS))}
def jarvis_inline_keywords(threshold: float) -> str:
    return "/".join(
        f"{phones} :1.0 #{threshold} @JARVIS_ALT_{i}"
        for i, phones in enumerate(JARVIS_PRONUNCIATIONS)
    )


JARVIS_INLINE_KEYWORDS = jarvis_inline_keywords(WAKEWORD_JARVIS_THRESHOLD)


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
    jarvis_threshold = WAKEWORD_JARVIS_THRESHOLD

    def __init__(
        self, directory: Path, threshold: float = 0.35, *,
        jarvis_threshold: float = WAKEWORD_JARVIS_THRESHOLD,
        trailing_blanks: int = WAKEWORD_KEYWORD_TRAILING_BLANKS,
    ):
        for value in (threshold, jarvis_threshold):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Keyword thresholds must be finite values between 0 and 1")
        if not isinstance(trailing_blanks, int) or isinstance(trailing_blanks, bool) or trailing_blanks < 1:
            raise ValueError("Trailing blanks must be a positive integer")
        self.threshold = threshold
        self.jarvis_threshold = jarvis_threshold
        self.trailing_blanks = trailing_blanks
        for name in MODEL_FILES[:4]:
            if not (directory / name).is_file():
                raise FileNotFoundError(directory / name)

        tokens = {line.split()[0] for line in
                  (directory / "tokens.txt").read_text(encoding="utf-8").splitlines()
                  if line.split()}
        if not all(set(p.split()) <= tokens for p in
                   (JARVIS_BASE_PRONUNCIATION, *JARVIS_PRONUNCIATIONS)):
            raise ValueError("Jarvis pronunciation tokens do not match the model")

        import sherpa_onnx

        # sherpa requires a keyword file and reads it during construction.
        # Build it separately so legacy downloaded files cannot add Wake up.
        with TemporaryDirectory(prefix="jarvis-keywords-") as folder:
            keywords_file = Path(folder) / "keywords.txt"
            keywords_file.write_text(
                JARVIS_BASE_PRONUNCIATION + " @JARVIS\n", encoding="utf-8")
            self._spotter = sherpa_onnx.KeywordSpotter(
                encoder=str(directory / MODEL_FILES[0]),
                decoder=str(directory / MODEL_FILES[1]),
                joiner=str(directory / MODEL_FILES[2]),
                tokens=str(directory / "tokens.txt"),
                keywords_file=str(keywords_file),
                num_threads=1, provider="cpu",
                max_active_paths=16,
                num_trailing_blanks=trailing_blanks,
                keywords_threshold=threshold,
                keywords_score=1.0,
            )
        self.reset()

    def reset(self) -> None:
        # A fresh stream removes acoustic state across microphone handoffs.
        self.last_detection_id: str | None = None
        self._stream = self._spotter.create_stream(jarvis_inline_keywords(self.jarvis_threshold))

    def predict(self, audio: np.ndarray) -> str | None:
        self.last_detection_id = None
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
                    self.last_detection_id = result
        return detected
