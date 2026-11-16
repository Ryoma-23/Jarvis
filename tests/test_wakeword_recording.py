import contextlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

import numpy as np

from scripts.record_wakeword_sample import main, record_sample
from scripts.evaluate_wakeword import audio_frames, validate_wav


class WakewordRecordingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name) / "sample.wav"
        self.device = SimpleNamespace(index=7, default_sample_rate=16000,
                                      input_channels=6, name="ReSpeaker", host_api_name="MME")
        patcher = patch("scripts.record_wakeword_sample.sd.InputStream")
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)
        self.stream = self.factory.return_value.__enter__.return_value
        self.stream.read.side_effect = lambda count: (np.tile(
            np.array([123, 456, 789, 0, 0, 0], dtype=np.int16), (count, 1)), False)

    def test_records_selected_channel_and_exact_length_in_evaluator_format(self):
        result = record_sample(self.output, 0.1, self.device)
        self.assertEqual(result["frames"], 1600)
        self.assertEqual(result["peak"], 123)
        self.assertEqual(result["rms"], 123)
        self.assertEqual([call.args[0] for call in self.stream.read.call_args_list], [1280, 320])
        self.assertEqual(self.factory.call_args.kwargs["channels"], 6)
        self.assertEqual(self.factory.call_args.kwargs["device"], 7)
        with wave.open(str(self.output), "rb") as source:
            self.assertEqual(source.getnchannels(), 1)
            self.assertEqual(source.getnframes(), 1600)
            frames = list(audio_frames(source, 0, validate_wav(source, 0)))
            self.assertTrue(np.all(frames[0] == 123))
        self.factory.return_value.__exit__.assert_called_once()

    def test_existing_file_is_preserved_without_opening_microphone(self):
        self.output.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            record_sample(self.output, 1, self.device)
        self.assertEqual(self.output.read_bytes(), b"existing")
        self.factory.assert_not_called()

    def test_invalid_durations_do_not_open_microphone(self):
        for duration in (0, -1, 601, float("nan"), float("inf")):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                record_sample(self.output, duration, self.device)
        self.factory.assert_not_called()

    def test_insufficient_channels_do_not_open_microphone(self):
        self.device.input_channels = 1
        with self.assertRaises(ValueError):
            record_sample(self.output, 1, self.device)
        self.factory.assert_not_called()

    def test_overflow_zero_input_and_interrupt_do_not_save(self):
        failures = [
            (np.ones((1280, 6), dtype=np.int16), True),
            (np.zeros((1280, 6), dtype=np.int16), False),
            KeyboardInterrupt(),
        ]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                self.stream.read.side_effect = None
                if isinstance(failure, BaseException):
                    self.stream.read.side_effect = failure
                    expected = KeyboardInterrupt
                else:
                    self.stream.read.return_value = failure
                    expected = RuntimeError
                with self.assertRaises(expected):
                    record_sample(self.output, 0.08, self.device)
                self.assertFalse(self.output.exists())
        self.assertEqual(self.factory.return_value.__exit__.call_count, 3)

    def test_negative_full_scale_peak_does_not_overflow(self):
        self.stream.read.side_effect = lambda count: (np.full((count, 6), -32768, dtype=np.int16), False)
        result = record_sample(self.output, 0.08, self.device)
        self.assertEqual(result["peak"], 32768)
        self.assertEqual(result["clipped_samples"], 1280)

    def test_file_created_during_capture_is_not_overwritten(self):
        def read(count):
            self.output.write_bytes(b"other writer")
            return np.ones((count, 6), dtype=np.int16), False
        self.stream.read.side_effect = read
        with self.assertRaises(FileExistsError):
            record_sample(self.output, 0.08, self.device)
        self.assertEqual(self.output.read_bytes(), b"other writer")

    def test_cli_countdown_and_saved_sample(self):
        with patch("scripts.record_wakeword_sample.find_wakeword_input_device", return_value=self.device), \
                patch("scripts.record_wakeword_sample.time.sleep") as sleep, \
                contextlib.redirect_stdout(io.StringIO()):
            result = main(["--output", str(self.output), "--seconds", "0.08", "--countdown", "2"])
        self.assertEqual(result, 0)
        self.assertEqual(sleep.call_count, 2)
        self.assertTrue(self.output.exists())


if __name__ == "__main__":
    unittest.main()
