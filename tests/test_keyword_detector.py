import json
import unittest
import tempfile
from pathlib import Path
import sys
from unittest.mock import Mock, patch
from types import SimpleNamespace
import numpy as np

from wakeword.keyword_detector import KeywordDetector, normalize_keyword, JARVIS_ALIAS_IDS, JARVIS_INLINE_KEYWORDS, JARVIS_PRONUNCIATIONS, JARVIS_BASE_PRONUNCIATION, MODEL_FILES, prepare_model
from wakeword.wakeword_listener import WakeWordListener


class KeywordDetectorTests(unittest.TestCase):
    def setUp(self):
        logger = patch("core.logger.tray_log")
        self.tray_log = logger.start()
        self.addCleanup(logger.stop)

    def test_constructor_applies_stricter_end_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for name in (*MODEL_FILES[:4], "keywords.txt"):
                (directory / name).touch()
            (directory / "keywords.txt").write_text("W EY1 K AH1 P @WAKE_UP\n", encoding="utf-8")
            tokens = sorted({token for p in (JARVIS_BASE_PRONUNCIATION, *JARVIS_PRONUNCIATIONS) for token in p.split()})
            (directory / "tokens.txt").write_text(
                "\n".join(f"{token} {i}" for i, token in enumerate(tokens)),
                encoding="utf-8",
            )
            factory = Mock()
            def check_keywords(**options):
                self.assertEqual(Path(options["keywords_file"]).read_text(encoding="utf-8"),
                                 JARVIS_BASE_PRONUNCIATION + " @JARVIS\n")
                self.assertNotEqual(Path(options["keywords_file"]), directory / "keywords.txt")
                return factory.return_value
            factory.side_effect = check_keywords
            with patch.dict(sys.modules, {"sherpa_onnx": SimpleNamespace(KeywordSpotter=factory)}):
                detector = KeywordDetector(directory)
            options = factory.call_args.kwargs
            self.assertEqual(options["num_trailing_blanks"], 4)
            self.assertEqual(options["keywords_threshold"], 0.35)
            inline = factory.return_value.create_stream.call_args.args[0]
            self.assertNotIn("WAKE_UP", inline)
            self.assertNotIn("#0.25", inline)
            self.assertEqual(inline.count("#0.35"), len(JARVIS_PRONUNCIATIONS))
            with patch.dict(sys.modules, {"sherpa_onnx": SimpleNamespace(KeywordSpotter=factory)}):
                custom = KeywordDetector(directory, 0.55, jarvis_threshold=0.65, trailing_blanks=8)
            self.assertEqual(factory.call_args.kwargs["keywords_threshold"], 0.55)
            self.assertEqual(factory.call_args.kwargs["num_trailing_blanks"], 8)
            custom.reset()
            custom_inline = factory.return_value.create_stream.call_args.args[0]
            self.assertEqual(custom_inline.count("#0.65"), len(JARVIS_PRONUNCIATIONS))
            self.assertNotIn("#0.35", custom_inline)
            self.assertEqual(custom.threshold, 0.55)
            self.assertEqual(custom.jarvis_threshold, 0.65)

    def test_invalid_tuning_parameters_fail_before_model_loading(self):
        for options in ({"threshold": float("nan")}, {"jarvis_threshold": 1.1},
                        {"threshold": -0.1}, {"trailing_blanks": 0}, {"trailing_blanks": 2.5}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                KeywordDetector(Path("missing-model"), **options)

    def test_distinct_aliases_normalize_to_jarvis(self):
        self.assertEqual(len(JARVIS_ALIAS_IDS), 7)
        for alias in JARVIS_ALIAS_IDS:
            self.assertEqual(normalize_keyword(alias), "Jarvis")
            self.assertIn("@" + alias, JARVIS_INLINE_KEYWORDS)
        self.assertIsNone(normalize_keyword("JARVIS_ALT_UNKNOWN"))

    def test_alias_detection_reaches_listener_callback(self):
        detector = KeywordDetector.__new__(KeywordDetector)
        detector.threshold = 0.35
        detector._stream = Mock()
        detector._spotter = Mock()
        detector._spotter.is_ready.side_effect = [True, False]
        detector._spotter.get_result.return_value = "JARVIS_ALT_1"
        listener = self.make_listener()
        listener._keyword_detector = detector
        listener._process_audio(np.zeros(1280, dtype=np.int16))
        listener._on_detected.assert_called_once_with(1.0)
        self.assertTrue(listener._pause_event.is_set())
        event = self.logged_event()
        self.assertEqual(event["sherpa_keyword_id"], "JARVIS_ALT_1")
        self.assertEqual(event["sherpa_pronunciation"], JARVIS_PRONUNCIATIONS[1])
        self.assertEqual(event["detectors"], ["sherpa_onnx"])
        self.assertIsNone(event["sherpa_score"])
        self.assertEqual(event["sherpa_score_status"], "unavailable")
        self.assertEqual(event["openwakeword_score"], 0.0)

    def test_pcm_conversion_and_keyword_reset(self):
        detector = KeywordDetector.__new__(KeywordDetector)
        detector._stream = Mock()
        detector._spotter = Mock()
        detector._spotter.is_ready.side_effect = [True, False]
        detector._spotter.get_result.return_value = 'JARVIS'
        self.assertEqual(detector.predict(np.array([-32768, 16384], dtype=np.int16)), 'Jarvis')
        rate, audio = detector._stream.accept_waveform.call_args.args
        self.assertEqual(rate, 16000)
        np.testing.assert_array_equal(audio, [-1.0, 0.5])
        detector._spotter.reset_stream.assert_called_once_with(detector._stream)

    def test_reset_discards_old_stream(self):
        detector = KeywordDetector.__new__(KeywordDetector)
        detector._spotter = Mock()
        detector._stream = object()
        detector.reset()
        self.assertIs(detector._stream, detector._spotter.create_stream.return_value)
        detector._spotter.create_stream.assert_called_once_with(JARVIS_INLINE_KEYWORDS)

    def make_listener(self, keyword=None, score=0.0):
        listener = WakeWordListener(Mock())
        listener._device = SimpleNamespace(default_sample_rate=16000)
        listener._model = Mock()
        listener._model.predict.return_value = {'hey_jarvis': score}
        listener._keyword_detector = Mock()
        listener._keyword_detector.last_detection_id = "JARVIS" if keyword else None
        listener._keyword_detector.threshold = 0.35
        listener._keyword_detector.predict.return_value = keyword
        listener._close_stream = Mock()
        return listener

    def logged_event(self):
        return json.loads(self.tray_log.call_args.args[0].split("candidate=", 1)[1])

    def test_logs_both_detectors_without_changing_activation(self):
        listener = self.make_listener("Jarvis", score=0.8)
        listener._process_audio(np.zeros(1280, dtype=np.int16))
        event = self.logged_event()
        self.assertEqual(event["detectors"], ["openwakeword", "sherpa_onnx"])
        self.assertEqual(event["decision"], "activate")
        self.assertEqual(event["sherpa_pronunciation"], JARVIS_BASE_PRONUNCIATION)
        self.assertEqual(event["sherpa_threshold"], 0.35)
        listener._on_detected.assert_called_once_with(1.0)

    def test_logs_openwakeword_score_as_its_own_score(self):
        listener = self.make_listener(score=0.8)
        listener._process_audio(np.zeros(1280, dtype=np.int16))
        event = self.logged_event()
        self.assertEqual(event["detectors"], ["openwakeword"])
        self.assertEqual(event["openwakeword_score"], 0.8)
        self.assertEqual(event["openwakeword_threshold"], 0.5)
        self.assertIsNone(event["sherpa_keyword_id"])
        listener._on_detected.assert_called_once_with(0.8)

    def test_logs_suppression_reasons_but_not_silent_frames(self):
        for reason in ("resume_guard", "cooldown", "silence"):
            with self.subTest(reason=reason):
                self.tray_log.reset_mock()
                listener = self.make_listener(None if reason == "silence" else "Jarvis")
                if reason == "resume_guard":
                    listener._detection_enabled_at = float("inf")
                elif reason == "cooldown":
                    listener._last_detection_time = float("inf")
                listener._process_audio(np.zeros(1280, dtype=np.int16))
                listener._on_detected.assert_not_called()
                if reason == "silence":
                    self.tray_log.assert_not_called()
                else:
                    self.assertEqual(self.logged_event()["decision"], reason)

    def test_log_write_failure_does_not_block_activation(self):
        listener = self.make_listener("Jarvis")
        self.tray_log.side_effect = OSError("disk unavailable")
        listener._process_audio(np.zeros(1280, dtype=np.int16))
        listener._close_stream.assert_called_once()
        listener._on_detected.assert_called_once_with(1.0)

    def test_detection_id_does_not_leak_into_next_frame_or_reset(self):
        detector = KeywordDetector.__new__(KeywordDetector)
        detector._stream = Mock()
        detector._spotter = Mock()
        detector._spotter.is_ready.side_effect = [True, False, False]
        detector._spotter.get_result.return_value = "JARVIS_ALT_2"
        self.assertEqual(detector.predict(np.zeros(1280, dtype=np.int16)), "Jarvis")
        self.assertEqual(detector.last_detection_id, "JARVIS_ALT_2")
        self.assertIsNone(detector.predict(np.zeros(1280, dtype=np.int16)))
        self.assertIsNone(detector.last_detection_id)
        detector.last_detection_id = "JARVIS_ALT_2"
        detector.reset()
        self.assertIsNone(detector.last_detection_id)

    def test_each_alias_releases_microphone_before_callback(self):
        for phrase in ('Jarvis',):
            with self.subTest(phrase=phrase):
                listener = self.make_listener(phrase)
                listener._on_detected.side_effect = lambda _: self.assertTrue(listener._pause_event.is_set())
                listener._process_audio(np.zeros(1280, dtype=np.int16))
                listener._close_stream.assert_called_once()
                listener._on_detected.assert_called_once_with(1.0)

    def test_removed_keywords_do_not_activate_listener(self):
        for result in ('WAKE_UP', 'WAKE_UP_JARVIS'):
            with self.subTest(result=result):
                self.assertIsNone(normalize_keyword(result))
                detector = KeywordDetector.__new__(KeywordDetector)
                detector._stream = Mock()
                detector._spotter = Mock()
                detector._spotter.is_ready.side_effect = [True, False]
                detector._spotter.get_result.return_value = result
                listener = self.make_listener()
                listener._keyword_detector = detector
                listener._process_audio(np.zeros(1280, dtype=np.int16))
                listener._on_detected.assert_not_called()
                self.assertFalse(listener._pause_event.is_set())

    def test_prepare_model_writes_only_jarvis_without_downloading(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for name in MODEL_FILES:
                (directory / name).touch()
            (directory / "en.phone").write_text(
                "JARVIS " + JARVIS_BASE_PRONUNCIATION + "\n", encoding="utf-8")
            (directory / "tokens.txt").write_text(
                "\n".join(f"{token} {i}" for i, token in enumerate(JARVIS_BASE_PRONUNCIATION.split())),
                encoding="utf-8")
            with patch("urllib.request.urlopen") as download:
                prepare_model(directory)
            download.assert_not_called()
            self.assertEqual((directory / "keywords.txt").read_text(encoding="utf-8"),
                             JARVIS_BASE_PRONUNCIATION + " @JARVIS\n")

    def test_guard_cooldown_and_silence_do_not_activate(self):
        for mode in ('guard', 'cooldown', 'silence'):
            listener = self.make_listener(None if mode == 'silence' else 'Jarvis')
            if mode == 'guard':
                listener._detection_enabled_at = float('inf')
            if mode == 'cooldown':
                listener._last_detection_time = float('inf')
            listener._process_audio(np.zeros(1280, dtype=np.int16))
            listener._on_detected.assert_not_called()

    def test_existing_detector_works_without_extra_model(self):
        listener = self.make_listener(score=0.8)
        listener._keyword_detector = None
        listener._process_audio(np.zeros(1280, dtype=np.int16))
        listener._on_detected.assert_called_once_with(0.8)

    def test_resume_resets_both_detectors(self):
        listener = self.make_listener()
        listener._reset_model_state()
        listener._model.reset.assert_called_once()
        listener._keyword_detector.reset.assert_called_once()


if __name__ == '__main__':
    unittest.main()
