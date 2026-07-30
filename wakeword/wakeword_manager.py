import threading
from collections.abc import Callable

from wakeword.wakeword_listener import WakeWordListener


class WakeWordManager:
    """
    WakeWordListenerとJarvis本体の間を管理するクラス。

    Wake Word検知後の二重起動防止、
    待機の一時停止・再開、
    Realtime会話中の状態管理、
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
        self._is_conversing = False

    @property
    def is_started(self) -> bool:
        with self._state_lock:
            return self._is_started

    @property
    def is_activating(self) -> bool:
        with self._state_lock:
            return self._is_activating

    @property
    def is_conversing(self) -> bool:
        with self._state_lock:
            return self._is_conversing

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
            self._is_conversing = False

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
                self._is_conversing = False

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
            self._is_conversing = False

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

    def prepare_for_conversation(
        self,
        source: str = "unknown",
    ) -> None:
        """
        Realtimeがマイクを取得する前に呼び出す。

        Wake Word側のマイクを確実に解放し、
        Realtime接続処理中の状態へ移行する。
        """

        with self._state_lock:
            if not self._is_started:
                return

            self._is_activating = True
            self._is_conversing = False

        print(
            "[WakeWordManager] "
            "Realtime開始準備に入りました。"
            f" source={source}"
        )

        # Wake Word検知経由ではすでに停止済みだが、
        # 手動接続時にも確実にマイクを渡せるようにする。
        self._listener.pause()

    def conversation_started(
        self,
        source: str = "unknown",
    ) -> None:
        """
        Realtime接続が成功したときに呼び出す。
        """

        with self._state_lock:
            if not self._is_started:
                return

            self._is_activating = False
            self._is_conversing = True

        print(
            "[WakeWordManager] "
            "Realtime会話を開始しました。"
            f" source={source}"
        )

    def resume(self) -> None:
        """
        Wake Word待機を再開する。

        Realtime会話中に手動で呼ばれた場合は、
        マイク競合を防ぐため再開しない。
        """

        with self._state_lock:
            if not self._is_started:
                return

            if self._is_conversing:
                print(
                    "[WakeWordManager] "
                    "Realtime会話中のため"
                    "Wake Word待機を再開しません。"
                )
                return

            self._is_activating = False

        print(
            "[WakeWordManager] "
            "Wake Word待機へ戻ります。"
        )

        self._listener.resume()

    def conversation_finished(
        self,
        reason: str = "unknown",
    ) -> None:
        """
        Realtime会話が終了し、
        Realtime側のマイクが解放された後に呼び出す。
        """

        with self._state_lock:
            if not self._is_started:
                return

            self._is_activating = False
            self._is_conversing = False

        print(
            "[WakeWordManager] "
            "Realtime会話が終了しました。"
            f" reason={reason}"
        )

        self._listener.resume()

    def activation_failed(self) -> None:
        """
        Window表示やRealtime開始命令の送信に失敗した場合、
        Wake Word待機へ戻す。
        """

        print(
            "[WakeWordManager] "
            "Jarvis起動に失敗したため待機へ戻ります。"
        )

        with self._state_lock:
            if not self._is_started:
                return

            self._is_activating = False
            self._is_conversing = False

        self._listener.resume()

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

            if self._is_conversing:
                print(
                    "[WakeWordManager] "
                    "Realtime会話中のため"
                    "Wake Word検知を無視します。"
                )
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