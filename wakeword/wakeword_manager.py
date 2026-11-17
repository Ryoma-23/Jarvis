import threading
from collections.abc import Callable
from enum import Enum
from typing import Protocol
from uuid import uuid4


class WakeWordListenerProtocol(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...


class WakeWordState(str, Enum):
    STOPPED = "stopped"
    WAITING = "waiting"
    ACTIVATING = "activating"
    CONNECTING = "connecting"
    CONVERSING = "conversing"


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
        on_activate_jarvis: Callable[[str], bool | None],
        listener_factory: Callable[
            [Callable[[float], None]],
            WakeWordListenerProtocol,
        ] | None = None,
    ) -> None:
        self._on_activate_jarvis = on_activate_jarvis

        if listener_factory is None:
            from wakeword.wakeword_listener import (
                WakeWordListener,
            )

            listener_factory = WakeWordListener

        self._listener = listener_factory(
            self._on_wakeword_detected,
        )

        self._lifecycle_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self._state = WakeWordState.STOPPED
        self._active_session_id: str | None = None
        self._active_source: str | None = None

    @property
    def state(self) -> WakeWordState:
        with self._state_lock:
            return self._state

    @property
    def active_session_id(self) -> str | None:
        with self._state_lock:
            return self._active_session_id

    @property
    def active_source(self) -> str | None:
        with self._state_lock:
            return self._active_source

    @property
    def is_started(self) -> bool:
        return self.state is not WakeWordState.STOPPED

    @property
    def is_activating(self) -> bool:
        return self.state in {
            WakeWordState.ACTIVATING,
            WakeWordState.CONNECTING,
        }

    @property
    def is_conversing(self) -> bool:
        return self.state is WakeWordState.CONVERSING

    def start(self) -> bool:
        """
        Wake Word待機を開始する。
        複数回呼ばれても二重起動しない。
        """

        with self._lifecycle_lock:
            with self._state_lock:
                if self._state is not WakeWordState.STOPPED:
                    print(
                        "[WakeWordManager] "
                        "すでに起動しています。"
                    )
                    return False

                self._state = WakeWordState.WAITING
                self._clear_active_session_locked()

            print(
                "[WakeWordManager] "
                "Wake Word待機を開始します。"
            )

            try:
                self._listener.start()

            except Exception:
                with self._state_lock:
                    self._state = WakeWordState.STOPPED
                    self._clear_active_session_locked()

                raise

        return True

    def stop(self) -> bool:
        """
        Jarvis終了時にWake Word待機を終了する。
        """

        with self._lifecycle_lock:
            with self._state_lock:
                if self._state is WakeWordState.STOPPED:
                    return False

                self._state = WakeWordState.STOPPED
                self._clear_active_session_locked()

            print(
                "[WakeWordManager] "
                "Wake Word待機を終了します。"
            )

            self._listener.stop()
        return True

    def pause(self) -> bool:
        """
        Realtime会話などがマイクを使用するときに
        Wake Word側を一時停止する。
        """

        with self._state_lock:
            if self._state is WakeWordState.STOPPED:
                return False

            self._listener.pause()
        return True

    def prepare_for_conversation(
        self,
        source: str = "unknown",
        session_id: str | None = None,
    ) -> bool:
        """
        Realtimeがマイクを取得する前に呼び出す。

        Wake Word側のマイクを確実に解放し、
        Realtime接続処理中の状態へ移行する。
        """

        with self._state_lock:
            if self._state is WakeWordState.STOPPED:
                return False

            if (
                self._state is WakeWordState.WAITING
                and source == "wakeword"
            ):
                print(
                    "[WakeWordManager] "
                    "有効なWake Wordセッションではないため"
                    "Realtime開始を拒否します。"
                    f" session_id={session_id}"
                )
                return False

            if self._state in {
                WakeWordState.CONNECTING,
                WakeWordState.CONVERSING,
            }:
                return self._session_matches_locked(
                    session_id,
                )

            if self._state is WakeWordState.ACTIVATING:
                if not self._session_matches_locked(
                    session_id,
                ):
                    return False

                resolved_session_id = (
                    self._active_session_id
                )

            else:
                resolved_session_id = (
                    self._normalize_session_id(
                        session_id,
                    )
                )
                self._active_session_id = (
                    resolved_session_id
                )

            try:
                # Wake Word検知経由ではすでに停止済みだが、
                # 手動接続時にも確実にマイクを渡せるようにする。
                self._listener.pause()

            except Exception:
                self._state = WakeWordState.WAITING
                self._clear_active_session_locked()
                self._listener.resume()
                raise

            if (
                source != "unknown"
                or self._active_source is None
            ):
                self._active_source = source

            active_source = self._active_source
            self._state = WakeWordState.CONNECTING

        print(
            "[WakeWordManager] "
            "Realtime開始準備に入りました。"
            f" source={active_source},"
            f" session_id={resolved_session_id}"
        )
        return True

    def conversation_started(
        self,
        source: str = "unknown",
        session_id: str | None = None,
    ) -> bool:
        """
        Realtime接続が成功したときに呼び出す。
        """

        with self._state_lock:
            if self._state is WakeWordState.CONVERSING:
                return self._session_matches_locked(
                    session_id,
                )

            if self._state is not WakeWordState.CONNECTING:
                return False

            if not self._session_matches_locked(
                session_id,
            ):
                return False

            if source != "unknown":
                self._active_source = source

            active_session_id = self._active_session_id
            active_source = self._active_source
            self._state = WakeWordState.CONVERSING

        print(
            "[WakeWordManager] "
            "Realtime会話を開始しました。"
            f" source={active_source},"
            f" session_id={active_session_id}"
        )
        return True

    def resume(self) -> bool:
        """
        Wake Word待機を再開する。

        Realtime接続中または会話中に手動で呼ばれた場合は、
        マイク競合を防ぐため再開しない。
        """

        with self._state_lock:
            if self._state is WakeWordState.STOPPED:
                return False

            if self._state in {
                WakeWordState.CONNECTING,
                WakeWordState.CONVERSING,
            }:
                print(
                    "[WakeWordManager] "
                    "Realtime使用中のため"
                    "Wake Word待機を再開しません。"
                )
                return False

            self._listener.resume()
            self._state = WakeWordState.WAITING
            self._clear_active_session_locked()

        print(
            "[WakeWordManager] "
            "Wake Word待機へ戻ります。"
        )

        return True

    def conversation_finished(
        self,
        reason: str = "unknown",
        session_id: str | None = None,
    ) -> bool:
        """
        Realtime会話が終了し、
        Realtime側のマイクが解放された後に呼び出す。
        """

        with self._state_lock:
            if self._state not in {
                WakeWordState.ACTIVATING,
                WakeWordState.CONNECTING,
                WakeWordState.CONVERSING,
            }:
                return False

            if not self._session_matches_locked(
                session_id,
            ):
                return False

            finished_session_id = self._active_session_id
            self._listener.resume()
            self._state = WakeWordState.WAITING
            self._clear_active_session_locked()

        print(
            "[WakeWordManager] "
            "Realtime会話が終了しました。"
            f" reason={reason},"
            f" session_id={finished_session_id}"
        )

        return True

    def activation_failed(
        self,
        session_id: str | None = None,
    ) -> bool:
        """
        Window表示やRealtime開始命令の送信に失敗した場合、
        Wake Word待機へ戻す。
        """

        with self._state_lock:
            if self._state not in {
                WakeWordState.ACTIVATING,
                WakeWordState.CONNECTING,
            }:
                return False

            if not self._session_matches_locked(
                session_id,
            ):
                return False

            failed_session_id = self._active_session_id
            self._listener.resume()
            self._state = WakeWordState.WAITING
            self._clear_active_session_locked()

        print(
            "[WakeWordManager] "
            "Jarvis起動に失敗したため待機へ戻ります。"
            f" session_id={failed_session_id}"
        )

        return True

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
            if self._state is not WakeWordState.WAITING:
                print(
                    "[WakeWordManager] "
                    "待機状態ではないため"
                    "Wake Word検知を無視します。"
                    f" state={self._state.value}"
                )
                return

            session_id = uuid4().hex

            self._state = WakeWordState.ACTIVATING
            self._active_session_id = session_id
            self._active_source = "wakeword"

        print(
            "[WakeWordManager] "
            f"Wake Word検知 score={score:.3f},"
            f" session_id={session_id}"
        )

        # Window処理でWakeWordListenerの内部スレッドを
        # 長時間止めないよう、別スレッドで実行する。
        activation_thread = threading.Thread(
            target=self._activate_jarvis,
            args=(session_id,),
            name="WakeWordActivation",
            daemon=True,
        )

        activation_thread.start()

    def _activate_jarvis(
        self,
        session_id: str,
    ) -> None:
        try:
            success = self._on_activate_jarvis(
                session_id,
            )

            if success is False:
                self.activation_failed(
                    session_id=session_id,
                )

        except Exception as error:
            print(
                "[WakeWordManager] "
                "Jarvis起動処理でエラーが発生しました。"
            )
            print(
                "[WakeWordManager] "
                f"{type(error).__name__}: {error}"
            )

            self.activation_failed(
                session_id=session_id,
            )

    def _normalize_session_id(
        self,
        session_id: str | None,
    ) -> str:
        if session_id is not None:
            normalized = str(session_id).strip()

            if normalized:
                return normalized

        return uuid4().hex

    def _session_matches_locked(
        self,
        session_id: str | None,
    ) -> bool:
        if self._active_session_id is None:
            return session_id is None

        if session_id is None:
            # 既存呼び出しとの互換性を維持する。
            return True

        return session_id == self._active_session_id

    def _clear_active_session_locked(self) -> None:
        self._active_session_id = None
        self._active_source = None
