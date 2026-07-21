import queue
import threading
import time
from collections.abc import Callable

import numpy as np
import openwakeword
import sounddevice as sd
from openwakeword.model import Model

from core.config import (
    WAKEWORD_AUDIO_QUEUE_SIZE,
    WAKEWORD_CAPTURE_CHANNELS,
    WAKEWORD_MIC_CHANNEL_INDEX,
    WAKEWORD_COOLDOWN_SECONDS,
    WAKEWORD_DTYPE,
    WAKEWORD_MODEL_NAME,
    WAKEWORD_TARGET_FRAME_SAMPLES,
    WAKEWORD_TARGET_SAMPLE_RATE,
    WAKEWORD_THRESHOLD,
)
from wakeword.audio_converter import (
    convert_sample_rate,
)
from wakeword.audio_device import (
    AudioInputDevice,
    find_wakeword_input_device,
)


class WakeWordListener:
    def __init__(
        self,
        on_detected: Callable[[float], None],
    ):
        self._on_detected = on_detected

        self._thread: threading.Thread | None = None
        self._stream: sd.InputStream | None = None
        self._model: Model | None = None
        self._device: AudioInputDevice | None = None

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()

        self._audio_queue: queue.Queue[np.ndarray] = (
            queue.Queue(
                maxsize=WAKEWORD_AUDIO_QUEUE_SIZE
            )
        )

        self._last_detection_time = 0.0
        self._detected_model_key: str | None = None

    @property
    def is_running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
        )

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def start(self) -> None:
        if self.is_running:
            print(
                "[WakeWord] すでに起動しています。"
            )
            return

        self._stop_event.clear()
        self._pause_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            name="WakeWordListener",
            daemon=True,
        )

        self._thread.start()

    def pause(self) -> None:
        if not self.is_running:
            return

        print("[WakeWord] 一時停止します。")

        self._pause_event.set()
        self._close_stream()
        self._clear_audio_queue()

    def resume(self) -> None:
        if not self.is_running:
            return

        print("[WakeWord] 待機を再開します。")

        self._clear_audio_queue()
        self._pause_event.clear()

    def stop(self) -> None:
        print("[WakeWord] 終了します。")

        self._stop_event.set()
        self._pause_event.clear()

        self._close_stream()
        self._clear_audio_queue()

        if self._thread is not None:
            self._thread.join(timeout=5.0)

        self._thread = None
        self._model = None
        self._device = None

    def _load_model(self) -> None:
        print(
            "[WakeWord] openWakeWordモデルを"
            "読み込みます。"
        )

        openwakeword.utils.download_models()

        self._model = Model(
            inference_framework="onnx"
        )

        print(
            "[WakeWord] モデルを読み込みました。"
        )

        print(
            "[WakeWord] 利用可能モデル:",
            list(self._model.models.keys()),
        )

    def _open_stream(self) -> None:
        if self._stream is not None:
            return

        self._device = find_wakeword_input_device()

        source_sample_rate = (
            self._device.default_sample_rate
        )

        # openWakeWordへ80ms単位で渡すため、
        # 取得側も80ms単位にする。
        capture_block_size = int(
            source_sample_rate * 0.08
        )

        print(
            "[WakeWord] マイクを開始します。"
        )
        print(
            f"[WakeWord] device_index="
            f"{self._device.index}"
        )
        print(
            f"[WakeWord] device_name="
            f"{self._device.name}"
        )
        print(
            f"[WakeWord] host_api="
            f"{self._device.host_api_name}"
        )
        print(
            f"[WakeWord] capture_sample_rate="
            f"{source_sample_rate}"
        )
        print(
            f"[WakeWord] capture_block_size="
            f"{capture_block_size}"
        )
        print(
            f"[WakeWord] capture_channels="
            f"{WAKEWORD_CAPTURE_CHANNELS}"
        )
        print(
            f"[WakeWord] mic_channel_index="
            f"{WAKEWORD_MIC_CHANNEL_INDEX}"
        )

        self._stream = sd.InputStream(
            device=self._device.index,
            samplerate=source_sample_rate,
            blocksize=capture_block_size,
            channels=WAKEWORD_CAPTURE_CHANNELS,
            dtype=WAKEWORD_DTYPE,
            callback=self._audio_callback,
        )

        self._stream.start()

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None

        if stream is None:
            return

        try:
            stream.stop()
        except Exception as error:
            print(
                "[WakeWord] マイク停止時の警告:",
                error,
            )

        try:
            stream.close()
        except Exception as error:
            print(
                "[WakeWord] マイク解放時の警告:",
                error,
            )

        print(
            "[WakeWord] マイクを解放しました。"
        )

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status,
    ) -> None:
        if status:
            print(
                "[WakeWord] 音声入力警告:",
                status,
            )

        if self._pause_event.is_set():
            return

        if indata.ndim != 2:
            print(
                "[WakeWord] 想定外の音声データ形式です。"
                f" shape={indata.shape}"
            )
            return

        if (
            WAKEWORD_MIC_CHANNEL_INDEX
            >= indata.shape[1]
        ):
            print(
                "[WakeWord] 指定したマイクチャンネルが"
                "存在しません。"
                f" channel_index="
                f"{WAKEWORD_MIC_CHANNEL_INDEX},"
                f" available_channels="
                f"{indata.shape[1]}"
            )
            return

        audio = indata[
            :,
            WAKEWORD_MIC_CHANNEL_INDEX,
        ].copy()

        try:
            self._audio_queue.put_nowait(audio)

        except queue.Full:
            # 処理が追いつかない場合は古い音声を捨て、
            # 現在に近い音声を優先する。
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                pass

            try:
                self._audio_queue.put_nowait(audio)
            except queue.Full:
                pass

    def _clear_audio_queue(self) -> None:
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def _find_jarvis_score(
        self,
        predictions: dict[str, float],
    ) -> float:
        if self._detected_model_key is not None:
            return float(
                predictions.get(
                    self._detected_model_key,
                    0.0,
                )
            )

        expected_name = (
            WAKEWORD_MODEL_NAME
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

        for model_key, score in predictions.items():
            normalized_key = (
                model_key
                .lower()
                .replace("-", "_")
                .replace(" ", "_")
            )

            if (
                normalized_key == expected_name
                or "jarvis" in normalized_key
            ):
                self._detected_model_key = model_key

                print(
                    "[WakeWord] Jarvisモデルを"
                    f"選択しました: {model_key}"
                )

                return float(score)

        return 0.0

    def _process_audio(
        self,
        captured_audio: np.ndarray,
    ) -> None:
        if self._device is None:
            return

        if self._model is None:
            return

        converted_audio = convert_sample_rate(
            audio=captured_audio,
            source_sample_rate=(
                self._device.default_sample_rate
            ),
            target_sample_rate=(
                WAKEWORD_TARGET_SAMPLE_RATE
            ),
        )

        if (
            len(converted_audio)
            != WAKEWORD_TARGET_FRAME_SAMPLES
        ):
            print(
                "[WakeWord] 変換後フレーム長が"
                "想定と異なります。"
                f" expected="
                f"{WAKEWORD_TARGET_FRAME_SAMPLES},"
                f" actual={len(converted_audio)}"
            )
            return

        predictions = self._model.predict(
            converted_audio
        )

        jarvis_score = self._find_jarvis_score(
            predictions
        )

        # デバッグ時にスコア推移を確認したい場合のみ
        # コメントアウトを解除する。
        #
        # if jarvis_score >= 0.05:
        #     print(
        #         f"[WakeWord] score="
        #         f"{jarvis_score:.3f}"
        #     )

        if jarvis_score < WAKEWORD_THRESHOLD:
            return

        current_time = time.monotonic()

        elapsed = (
            current_time
            - self._last_detection_time
        )

        if elapsed < WAKEWORD_COOLDOWN_SECONDS:
            return

        self._last_detection_time = current_time

        print()
        print(
            "[WakeWord] Wake Wordを"
            "検知しました。"
        )
        print(
            f"[WakeWord] score="
            f"{jarvis_score:.3f}"
        )
        print()

        # Realtime側へマイクを渡せるよう、
        # 検知直後にWake Wordマイクを解放する。
        self._pause_event.set()
        self._close_stream()
        self._clear_audio_queue()

        self._on_detected(jarvis_score)

    def _run(self) -> None:
        print(
            "[WakeWord] 待機スレッドを"
            "開始します。"
        )

        try:
            self._load_model()

            while not self._stop_event.is_set():
                if self._pause_event.is_set():
                    self._close_stream()
                    self._stop_event.wait(0.1)
                    continue

                if self._stream is None:
                    self._open_stream()

                    print(
                        "[WakeWord] "
                        "「Hey Jarvis」を待機中です。"
                    )

                try:
                    captured_audio = (
                        self._audio_queue.get(
                            timeout=0.5
                        )
                    )
                except queue.Empty:
                    continue

                self._process_audio(
                    captured_audio
                )

        except Exception as error:
            print(
                "[WakeWord] 実行中に"
                "エラーが発生しました。"
            )
            print(
                f"[WakeWord] {type(error).__name__}: "
                f"{error}"
            )

        finally:
            self._close_stream()
            self._clear_audio_queue()
            self._model = None
            self._device = None

            print(
                "[WakeWord] 待機スレッドを"
                "終了しました。"
            )