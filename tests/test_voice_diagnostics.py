import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routes import voice_diagnostics as diag


class VoiceDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.patch = patch.object(diag, "SAVE_DIR", self.directory)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        app = FastAPI()
        app.include_router(diag.router)
        self.client = TestClient(app)
        self.payload = {"id": str(uuid4()), "started_at": "2026-11-17T00:00:00Z", "events": []}

    def post(self):
        return self.client.post("/voice-diagnostics", json=self.payload)

    def test_transcript_is_stripped_without_consent_and_complete_is_idempotent(self):
        self.payload.update(complete=True, events=[{"ms": 1, "kind": "transcript", "transcript": "private"}])
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().status_code, 200)
        saved = json.loads(next(self.directory.glob("*.json")).read_text(encoding="utf-8"))
        self.assertIsNone(saved["events"][0]["transcript"])
        self.payload["events"].append({"ms": 2, "kind": "stop"})
        self.assertEqual(self.post().status_code, 409)

    def test_consent_preserves_text_and_rejects_arbitrary_payload(self):
        self.payload.update(include_transcript=True, events=[{"ms": 1, "kind": "transcript", "transcript": "元気？"}])
        self.assertEqual(self.post().status_code, 200)
        saved = json.loads(next(self.directory.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(saved["events"][0]["transcript"], "元気？")
        self.payload["events"][0]["audio"] = "not allowed"
        self.assertEqual(self.post().status_code, 422)

    def test_validation_origin_and_path(self):
        self.payload["id"] = "../../outside"
        self.assertEqual(self.post().status_code, 422)
        self.assertEqual(self.client.post("/voice-diagnostics", json={}, headers={"Origin": "https://other.example"}).status_code, 403)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_body_limit_and_save_failure(self):
        self.assertEqual(self.client.post("/voice-diagnostics", content=b"x" * 4_000_001).status_code, 413)
        with patch.object(diag, "save_snapshot", side_effect=OSError):
            self.assertEqual(self.post().status_code, 503)

    def test_latency_handles_request_before_transcription(self):
        events = [
            {"ms": 0, "kind": "trial", "trial": 1},
            {"ms": 100, "kind": "speech_stop", "item": "i"},
            {"ms": 110, "kind": "response_request", "item": "i"},
            {"ms": 120, "kind": "response_created", "response": "r"},
            {"ms": 160, "kind": "transcript", "item": "i"},
            {"ms": 200, "kind": "audio_start", "response": "r"},
            {"ms": 220, "kind": "mark", "trial": 1, "value": "missed"},
        ]
        self.payload["events"] = events
        report = self.post().json()["report"]
        self.assertEqual(report["metrics"]["transcript_to_request"]["mean_ms"], -50)
        self.assertEqual(report["metrics"]["stop_to_audio"]["mean_ms"], 100)
        self.assertEqual(report["manual_by_scenario"]["quiet"]["reported_success_rate"], 0)

    def test_ambiguous_and_cross_session_responses_are_not_linked(self):
        self.payload["events"] = [
            {"ms": 1, "kind": "response_request", "item": "a", "session": "one"},
            {"ms": 2, "kind": "response_request", "item": "b", "session": "one"},
            {"ms": 3, "kind": "response_created", "response": "r", "session": "one"},
            {"ms": 4, "kind": "audio_start", "response": "r", "session": "one"},
            {"ms": 5, "kind": "response_request", "item": "a", "session": "two"},
            {"ms": 6, "kind": "response_created", "response": "r2", "session": "one"},
            {"ms": 7, "kind": "audio_start", "response": "r2", "session": "one"},
        ]
        self.assertEqual(self.post().json()["report"]["metrics"]["request_to_audio"]["count"], 0)

    def test_unmarked_trial_is_unknown_and_older_snapshot_is_rejected(self):
        self.payload["events"] = [{"ms": 0, "kind": "trial", "trial": 1}]
        report = self.post().json()["report"]
        self.assertIsNone(report["manual_by_scenario"]["quiet"]["reported_success_rate"])
        self.payload["events"] = []
        self.assertEqual(self.post().status_code, 409)


if __name__ == "__main__":
    unittest.main()
