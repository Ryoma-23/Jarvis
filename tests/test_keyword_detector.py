import unittest
import tempfile
from pathlib import Path
import sys
from unittest.mock import Mock, patch
from types import SimpleNamespace
import numpy as np

from wakeword.keyword_detector import KeywordDetector, normalize_keyword, JARVIS_ALIAS_IDS, JARVIS_INLINE_KEYWORDS, JARVIS_PRONUNCIATIONS, MODEL_FILES
from wakeword.wakeword_listener import WakeWordListener


class KeywordDetectorTests(unittest.TestCase):
    def setUp(self):
        logger = patch("core.logger.tray_log")
        logger.start()
        self.addCleanup(logger.stop)

    def test_constructor_applies_stricter_end_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for name in (*MODEL_FILES[:4], "keywords.txt"):
                (directory / name).touch()
            tokens = sorted({token for p in JARVIS_PRONUNCIATIONS for token in p.split()})
            (directory / "tokens.txt").write_text(
                "\n".join(f"{token} {i}" for i, token in enumerate(tokens)),
                encoding="utf-8",
            )
            factory = Mock()
            with patch.dict(sys.modules, {"sherpa_onnx": SimpleNamespace(KeywordSpotter=factory)}):
                detector = KeywordDetector(directory)
            options = factory.call_args.kwargs
            self.assertEqual(options["num_trailing_blanks"], 4)
            self.assertEqual(options["keywords_threshold"], 0.35)
            inline = factory.return_value.create_stream.call_args.args[0]
            self.assertNotIn("#0.25", inline)
            self.assertEqual(inline.count("#0.35"), len(JARVIS_PRONUNCIATIONS))

    def test_distinct_aliases_normalize_to_jarvis(self):
        self.assertEqual(len(JARVIS_ALIAS_IDS), 7)
        for alias in JARVIS_ALIAS_IDS:
            self.assertEqual(normalize_keyword(alias), "Jarvis")
            self.assertIn("@" + alias, JARVIS_INLINE_KEYWORDS)
        self.assertIsNone(normalize_keyword("JARVIS_ALT_UNKNOWN"))

    def test_alias_detection_reaches_listener_callback(self):
        detector = KeywordDetector.__new__(KeywordDetector)
        detector._stream = Mock()
        detector._spotter = Mock()
        detector._spotter.is_ready.side_effect = [True, False]
        detector._spotter.get_result.return_value = "JARVIS_ALT_1"
        listener = self.make_listener()
        listener._keyword_detector = detector
        listener._process_audio(np.zeros(1280, dtype=np.int16))
        listener._on_detected.assert_called_once_with(1.0)
        self.assertTrue(listener._pause_event.is_set())

    def test_pcm_conversion_and_keyword_reset(self):
        detector = KeywordDetector.__new__(KeywordDetector)
        detector._stream = Mock()
        detector._spotter = Mock()
        detector._spotter.is_ready.side_effect = [True, False]
        detector._spotter.get_result.return_value = 'WAKE_UP_JARVIS'
        self.assertEqual(detector.predict(np.array([-32768, 16384], dtype=np.int16)), 'Wake Up Jarvis')
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
        listener._keyword_detector.predict.return_value = keyword
        listener._close_stream = Mock()
        return listener

    def test_each_alias_releases_microphone_before_callback(self):
        for phrase in ('Jarvis', 'Wake Up', 'Wake Up Jarvis'):
            with self.subTest(phrase=phrase):
                listener = self.make_listener(phrase)
                listener._on_detected.side_effect = lambda _: self.assertTrue(listener._pause_event.is_set())
                listener._process_audio(np.zeros(1280, dtype=np.int16))
                listener._close_stream.assert_called_once()
                listener._on_detected.assert_called_once_with(1.0)

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
