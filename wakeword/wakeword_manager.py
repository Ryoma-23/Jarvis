import threading
from collections.abc import Callable

from wakeword.wakeword_listener import WakeWordListener


class WakeWordManager:
    """
    WakeWordListenerとJarvis本体の間を管理するクラス。

    Wake Word検知後の二重起動防止、
    待機の一時停止・再開、
    Jarvis終了時の停止処理を担当する。
    """

    def __init__(
        self,
        on_activate_jarvis: Callable[[], None],
    ) -> None:
        self._on_activate_jarvis = on_activate_jarvis

        self._listener = WakeWordListener(
            on_detected=self._on_wakeword_detected,
        )

        self._state_lock = threading.Lock()

        self._is_started = False
        self._is_activating = False

    @property
    def is_started(self) -> bool:
        with self._state_lock:
            return self._is_started

    @property
    def is_activating(self) -> bool:
        with self._state_lock:
            return self._is_activating

    def start(self) -> None:
        """
        Wake Word待機を開始する。
        複数回呼ばれても二重起動しない。
        """

        with self._state_lock:
            if self._is_started:
                print(
                    "[WakeWordManager] "
                    "すでに起動しています。"
                )
                return

            self._is_started = True
            self._is_activating = False

        print(
            "[WakeWordManager] "
            "Wake Word待機を開始します。"
        )

        try:
            self._listener.start()

        except Exception:
            with self._state_lock:
                self._is_started = False
                self._is_activating = False

            raise

    def stop(self) -> None:
        """
        Jarvis終了時にWake Word待機を終了する。
        """

        with self._state_lock:
            if not self._is_started:
                return

            self._is_started = False
            self._is_activating = False

        print(
            "[WakeWordManager] "
            "Wake Word待機を終了します。"
        )

        self._listener.stop()

    def pause(self) -> None:
        """
        Realtime会話などがマイクを使用するときに
        Wake Word側を一時停止する。
        """

        if not self.is_started:
            return

        self._listener.pause()

    def resume(self) -> None:
        """
        Realtime会話終了後にWake Word待機を再開する。
        """

        with self._state_lock:
            if not self._is_started:
                return

            self._is_activating = False

        print(
            "[WakeWordManager] "
            "Wake Word待機へ戻ります。"
        )

        self._listener.resume()

    def conversation_finished(self) -> None:
        """
        Jarvisとの会話終了時に呼び出す。
        現時点ではresume()と同じ役割。
        """

        self.resume()

    def activation_failed(self) -> None:
        """
        Window表示やRealtime開始に失敗した場合、
        Wake Word待機へ戻す。
        """

        print(
            "[WakeWordManager] "
            "Jarvis起動に失敗したため待機へ戻ります。"
        )

        self.resume()

    def _on_wakeword_detected(
        self,
        score: float,
    ) -> None:
        """
        WakeWordListenerから呼ばれるコールバック。

        この時点でWakeWordListener側のマイクは
        すでに解放されている。
        """

        with self._state_lock:
            if not self._is_started:
                return

            if self._is_activating:
                print(
                    "[WakeWordManager] "
                    "Jarvisはすでに起動処理中です。"
                )
                return

            self._is_activating = True

        print(
            "[WakeWordManager] "
            f"Wake Word検知 score={score:.3f}"
        )

        # Window処理でWakeWordListenerの内部スレッドを
        # 長時間止めないよう、別スレッドで実行する。
        activation_thread = threading.Thread(
            target=self._activate_jarvis,
            name="WakeWordActivation",
            daemon=True,
        )

        activation_thread.start()

    def _activate_jarvis(self) -> None:
        try:
            self._on_activate_jarvis()

        except Exception as error:
            print(
                "[WakeWordManager] "
                "Jarvis起動処理でエラーが発生しました。"
            )
            print(
                "[WakeWordManager] "
                f"{type(error).__name__}: {error}"
            )

            self.activation_failed()