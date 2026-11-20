import io
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.speaker_service import SpeakerService, SpeakerError, decode_audio
from app.routes import speaker


def wav(seconds=3, rate=16000, amplitude=.1):
    audio = amplitude * np.sin(np.arange(int(rate * seconds)) * (2 * np.pi * 220 / rate))
    output = io.BytesIO()
    with wave.open(output, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        f.writeframes((audio * 32767).astype("<i2").tobytes())
    return output.getvalue()


class SpeakerServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = SpeakerService(self.root, embedder=lambda _: np.array([1., 0., 0.]))

    def registered(self):
        profile = self.service.create()["id"]
        for i in range(8): self.service.enroll(profile, i, wav())
        self.service.activate(profile)
        return profile

    def test_enrollment_requires_eight_distinct_prompts(self):
        p = self.service.create()["id"]
        self.service.enroll(p, 0, wav())
        with self.assertRaises(SpeakerError) as error: self.service.activate(p)
        self.assertEqual(error.exception.code, "more_samples_required")
        with self.assertRaises(SpeakerError): self.service.enroll(p, 0, wav())
        self.assertEqual(len(list(self.root.rglob("*.wav"))), 1)

    def test_compare_never_persists_audio_or_updates_profile(self):
        profile = self.registered()
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        same = self.service.compare(wav())
        self.assertEqual(same["decision"], "owner_candidate")
        self.assertFalse(same["calibrated"])
        self.service.embedder = lambda _: np.array([0., 1., 0.])
        self.assertEqual(self.service.compare(wav())["decision"], "other_candidate")
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.service.delete(profile)
        self.assertIsNone(self.service.status()["active"])
        self.assertEqual(list(self.root.rglob("*.wav")), [])

    def test_short_silence_clipping_and_resampling(self):
        self.registered()
        self.assertEqual(self.service.compare(wav(.4))["decision"], "insufficient")
        short = self.service.compare(wav(.4))
        self.assertEqual(short['reason'], 'insufficient_audio')
        self.assertAlmostEqual(short['quality']['duration_s'], .4)
        self.assertAlmostEqual(short['quality']['energy_s'], .4)
        self.assertEqual(self.service.compare(wav(amplitude=0))["decision"], "insufficient")
        with self.assertRaises(SpeakerError): decode_audio(b"not WAV")
        audio, quality = decode_audio(wav(rate=48000), enrollment=True)
        self.assertEqual(len(audio), 48000)
        self.assertGreater(quality["energy_s"], 2)
        self.assertEqual(self.service.compare(wav(amplitude=1))["decision"], "insufficient")
        clipped = self.service.compare(wav(amplitude=1))
        self.assertEqual(clipped['reason'], 'clipped_audio')
        self.assertGreater(clipped['quality']['clipped_fraction'], .03)

    def test_no_registration_busy_missing_model_and_path_validation(self):
        with self.assertRaises(SpeakerError) as error: self.service.compare(wav())
        self.assertEqual(error.exception.code, "not_enrolled")
        self.service.work.acquire()
        try:
            with self.assertRaises(SpeakerError) as error: self.service.compare(wav())
            self.assertEqual(error.exception.code, "busy")
        finally: self.service.work.release()
        with self.assertRaises(SpeakerError) as error: SpeakerService(self.root).prepare()
        self.assertEqual(error.exception.code, "model_missing")
        with self.assertRaises(ValueError): self.service.path("../../outside")

    def test_api_bounds_origin_and_error_codes(self):
        app = FastAPI(); app.include_router(speaker.router)
        client = TestClient(app)
        with patch.object(speaker, "service", self.service):
            self.assertEqual(client.post("/speaker/profiles", headers={"Origin": "https://other.example"}).status_code, 403)
            profile = client.post("/speaker/profiles").json()["id"]
            path = f"/speaker/profiles/{profile}/samples/0"
            self.assertEqual(client.post(path, content=wav()).status_code, 415)
            self.assertEqual(client.post(path, content=b"x" * 1600001, headers={"Content-Type":"audio/wav"}).status_code, 413)
            self.assertEqual(client.post(path, content=wav(), headers={"Content-Type":"audio/wav"}).status_code, 200)
            self.assertEqual(client.post(f"/speaker/profiles/{profile}/activate").json()["detail"], "more_samples_required")


if __name__ == "__main__": unittest.main()
