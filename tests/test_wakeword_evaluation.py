import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

import numpy as np

from scripts.evaluate_wakeword import (
    TAIL_FRAMES, audio_frames, evaluate_file, main, summarize, validate_wav,
)


class WakewordEvaluationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.model = Mock()
        self.model.predict.return_value = {"hey_jarvis": 0.0}
        self.detector = Mock()
        self.detector.predict.return_value = None
        self.detector.last_detection_id = None
        self.detector.threshold = 0.35
        self.detector.jarvis_threshold = 0.35

    def wav(self, samples, rate=16000, width=2, name="clip.wav"):
        path = self.root / name
        samples = np.asarray(samples, dtype="<i2")
        with wave.open(str(path), "wb") as target:
            target.setnchannels(1 if samples.ndim == 1 else samples.shape[1])
            target.setsampwidth(width)
            target.setframerate(rate)
            target.writeframes(samples.tobytes())
        return path

    def test_channel_selection_partial_frame_and_tail(self):
        samples = np.column_stack((np.full(1600, 100), np.full(1600, 200)))
        path = self.wav(samples)
        with wave.open(str(path), "rb") as source:
            frames = list(audio_frames(source, 1, validate_wav(source, 1)))
        self.assertEqual(len(frames), 2 + TAIL_FRAMES)
        np.testing.assert_array_equal(frames[0], np.full(1280, 200))
        np.testing.assert_array_equal(frames[1][:320], np.full(320, 200))
        self.assertTrue(np.all(frames[1][320:] == 0))
        self.assertTrue(all(np.all(frame == 0) for frame in frames[2:]))

    def test_resampling_matches_live_block_conversion(self):
        path = self.wav(np.zeros(3840), rate=48000)
        result = evaluate_file(path, "negative", 0, self.model, self.detector)
        self.assertAlmostEqual(result["duration_seconds"], 0.08)
        self.assertFalse(result["detected"])
        for call in self.model.predict.call_args_list:
            self.assertEqual(call.args[0].shape, (1280,))
            self.assertEqual(call.args[0].dtype, np.int16)

    def test_both_detectors_and_cooldown_are_reported(self):
        path = self.wav(np.zeros(16000))
        self.model.predict.return_value = {"hey_jarvis": 0.8}
        self.detector.predict.return_value = "Jarvis"
        self.detector.last_detection_id = "JARVIS_ALT_2"
        result = evaluate_file(path, "positive", 0, self.model, self.detector)
        self.assertEqual(result["event_count"], 2)
        first, second = result["events"]
        self.assertEqual(first["detectors"], ["sherpa_onnx"])
        self.assertEqual(second["detectors"], ["openwakeword", "sherpa_onnx"])
        self.assertEqual(first["sherpa_keyword_id"], "JARVIS_ALT_2")
        self.assertIsNone(first["sherpa_score"])
        self.assertAlmostEqual(second["time_seconds"] - first["time_seconds"], 2.0)
        self.assertTrue(second["during_padding"])
        self.assertEqual(result["peak_openwakeword_score"], 0.8)

    def test_each_file_resets_models_and_does_not_apply_startup_guard(self):
        path = self.wav(np.zeros(2560))
        for _ in range(2):
            self.model.predict.side_effect = [{"hey_jarvis": 0.7}] * 2 + [{"hey_jarvis": 0.0}] * TAIL_FRAMES
            result = evaluate_file(path, "positive", 0, self.model, self.detector)
            self.assertEqual(result["event_count"], 1)
            self.assertEqual(result["events"][0]["time_seconds"], 0.16)
        self.assertEqual(self.model.reset.call_count, 2)
        self.assertEqual(self.detector.reset.call_count, 2)

    def test_summary_uses_clip_hits_and_unpadded_negative_duration(self):
        summary = summarize([
            {"label": "positive", "detected": True, "event_count": 3, "duration_seconds": 2},
            {"label": "positive", "detected": False, "event_count": 0, "duration_seconds": 2},
            {"label": "negative", "detected": True, "event_count": 2, "duration_seconds": 60},
        ])
        self.assertEqual(summary["positive_clip_detection_rate"], 0.5)
        self.assertEqual(summary["positive_clips_missed"], 1)
        self.assertEqual(summary["negative_events_per_hour"], 120)
        self.assertIsNone(summarize([])["positive_clip_detection_rate"])
        self.assertIsNone(summarize([])["negative_events_per_hour"])

    def test_installed_version_suffix_matches_live_listener(self):
        path = self.wav(np.zeros(1280))
        self.model.predict.return_value = {"hey_jarvis_v0.1": 0.8}
        result = evaluate_file(path, "positive", 0, self.model, self.detector)
        self.assertEqual(result["openwakeword_model"], "hey_jarvis_v0.1")
        self.assertTrue(result["detected"])

    def test_missing_detector_score_is_an_error_not_a_miss(self):
        path = self.wav(np.zeros(1280))
        self.model.predict.return_value = {"another_model": 0.8}
        with self.assertRaisesRegex(ValueError, "Missing openWakeWord"):
            evaluate_file(path, "positive", 0, self.model, self.detector)

    def test_invalid_audio_and_channel_are_rejected(self):
        for samples, width, channel in (([], 2, 0), ([0], 1, 0), ([0], 2, 1), ([0], 2, -1)):
            with self.subTest(width=width, channel=channel, samples=samples):
                path = self.wav(samples, width=width)
                with self.assertRaises(ValueError):
                    evaluate_file(path, "positive", channel, self.model, self.detector)

    def test_truncated_audio_is_rejected(self):
        path = self.wav(np.zeros(1280))
        path.write_bytes(path.read_bytes()[:-10])
        with self.assertRaisesRegex(ValueError, "truncated"):
            evaluate_file(path, "negative", 0, self.model, self.detector)

    def test_cli_writes_json_and_refuses_overwrite(self):
        path = self.wav(np.zeros(1280))
        output = self.root / "report.json"
        with patch("openwakeword.model.Model", return_value=self.model), \
                patch("scripts.evaluate_wakeword.KeywordDetector", return_value=self.detector), \
                contextlib.redirect_stderr(io.StringIO()):
            arguments = ["--negative", str(path), "--output", str(output)]
            self.assertEqual(main(arguments), 0)
            original = output.read_text(encoding="utf-8")
            self.assertEqual(json.loads(original)["summary"]["negative_events"], 0)
            self.assertEqual(main(arguments), 1)
            self.assertEqual(output.read_text(encoding="utf-8"), original)

    def test_duplicate_or_conflicting_labels_are_rejected(self):
        path = self.wav(np.zeros(1280))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(["--positive", str(path), "--negative", str(path)])
        self.assertEqual(error.exception.code, 2)

    def test_tuned_openwakeword_threshold_changes_events(self):
        path = self.wav(np.zeros(1280))
        self.model.predict.return_value = {"hey_jarvis": 0.6}
        baseline = evaluate_file(path, "positive", 0, self.model, self.detector)
        stricter = evaluate_file(path, "positive", 0, self.model, self.detector,
                                openwakeword_threshold=0.7)
        self.assertTrue(baseline["detected"])
        self.assertFalse(stricter["detected"])
        self.assertEqual(stricter["peak_openwakeword_score"], 0.6)

    def test_cli_tuning_is_passed_to_model_and_reported(self):
        path = self.wav(np.zeros(1280))
        output = self.root / "tuned.json"
        self.detector.predict.return_value = "Jarvis"
        self.detector.last_detection_id = "JARVIS_ALT_1"
        self.detector.jarvis_threshold = 0.65
        with patch("openwakeword.model.Model", return_value=self.model), \
                patch("scripts.evaluate_wakeword.KeywordDetector", return_value=self.detector) as factory, \
                contextlib.redirect_stderr(io.StringIO()):
            result = main(["--positive", str(path), "--output", str(output),
                           "--openwakeword-threshold", "0.7", "--sherpa-threshold", "0.55",
                           "--jarvis-threshold", "0.65", "--trailing-blanks", "8"])
        self.assertEqual(result, 0)
        self.assertEqual(factory.call_args.args[1], 0.55)
        self.assertEqual(factory.call_args.kwargs, {"jarvis_threshold": 0.65, "trailing_blanks": 8})
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["settings"]["openwakeword_threshold"], 0.7)
        self.assertEqual(report["settings"]["sherpa_base_threshold"], 0.55)
        self.assertEqual(report["settings"]["sherpa_alias_threshold"], 0.65)
        self.assertEqual(report["settings"]["sherpa_trailing_blanks"], 8)
        self.assertEqual(report["files"][0]["events"][0]["sherpa_threshold"], 0.65)

    def test_cli_rejects_invalid_tuning_before_model_loading(self):
        for option, value in (("--openwakeword-threshold", "nan"),
                              ("--sherpa-threshold", "inf"), ("--jarvis-threshold", "-0.1"),
                              ("--openwakeword-threshold", "1.1"), ("--trailing-blanks", "0")):
            with self.subTest(option=option, value=value), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main([option, value])
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
