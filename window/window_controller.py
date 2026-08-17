import json
import threading
from collections.abc import Callable

from core.config import (
    APP_WINDOW_TITLE,
    WINDOW_PAGE_READY_TIMEOUT_SECONDS,
)
from core.logger import window_log
from window.window_state import save_current_window_state
from window.windows_api import (
    bring_window_to_front_by_title,
    get_window_rect_by_title,
)


class WindowController:
    def __init__(
        self,
        on_realtime_window_closed: (
            Callable[[str, str], bool | None] | None
        ) = None,
    ):
        self.window = None
        self.is_window_visible = False
        self.is_shutting_down = False
        self.stop_control_server_func = None
        self._realtime_start_lock = threading.Lock()
        self._on_realtime_window_closed = (
            on_realtime_window_closed
        )
        self._active_realtime_session_id = None

    def set_window(self, window):
        self.window = window

    def set_stop_control_server_func(self, func):
        self.stop_control_server_func = func

    def show(self):
        if self.window is None:
            window_log("show命令を受け取りましたが、windowが存在しません。")
            return False

        window_log("Jarvisウィンドウを表示・復帰します。")

        try:
            self.window.show()
            self.window.restore()

            bring_window_to_front_by_title(APP_WINDOW_TITLE)

            self.is_window_visible = True

            return True

        except Exception as error:
            window_log(f"Jarvisウィンドウの表示・復帰に失敗しました: {error}")
            return False

    def hide(self):
        if self.window is None:
            window_log("hide命令を受け取りましたが、windowが存在しません。")
            return False

        try:
            window_log("Jarvisウィンドウを非表示にします。")

            save_current_window_state()

            self.window.hide()

            self.is_window_visible = False

            return True

        except Exception as error:
            window_log(f"Jarvisウィンドウの非表示に失敗しました: {error}")
            return False

    def destroy(self):
        self.is_shutting_down = True

        if self.window is None:
            window_log("destroy命令を受け取りましたが、windowが存在しません。")
            return False

        try:
            window_log("Jarvisウィンドウを終了します。")

            save_current_window_state()

            self.is_window_visible = False
            self.window.destroy()

            return True

        except Exception as error:
            window_log(f"Jarvisウィンドウ終了に失敗しました: {error}")
            return False

    def focus(self):
        if self.window is None:
            window_log("focus命令を受け取りましたが、windowが存在しません。")
            return False

        window_log("Jarvisウィンドウを前面に出します。")

        try:
            return bring_window_to_front_by_title(APP_WINDOW_TITLE)

        except Exception as error:
            window_log(f"Jarvisウィンドウの前面表示に失敗しました: {error}")
            return False

    def start_realtime(
        self,
        source: str,
        session_id: str,
        ready_timeout: float = (
            WINDOW_PAGE_READY_TIMEOUT_SECONDS
        ),
    ) -> bool:
        """
        ページの読み込み完了後、JavaScriptへ
        Realtime開始を依頼する。
        """

        normalized_source = str(source).strip()
        normalized_session_id = str(session_id).strip()

        if not normalized_source or not normalized_session_id:
            return False

        window = self.window

        if window is None or self.is_shutting_down:
            window_log(
                "Realtime開始命令を受け取りましたが、"
                "windowを使用できません。"
            )
            return False

        window_log(
            "Realtime開始前にページ準備を待機します。"
            f" source={normalized_source},"
            f" session_id={normalized_session_id}"
        )

        if not window.events.loaded.wait(ready_timeout):
            window_log(
                "ページ準備待機がタイムアウトしました。"
                f" session_id={normalized_session_id}"
            )
            return False

        with self._realtime_start_lock:
            if (
                self.window is not window
                or self.is_shutting_down
            ):
                return False

            source_json = json.dumps(
                normalized_source,
                ensure_ascii=False,
            )
            session_id_json = json.dumps(
                normalized_session_id,
                ensure_ascii=False,
            )
            script = (
                "(() => {"
                "const realtimeApi = window.jarvisRealtime;"
                "if (!realtimeApi || "
                "typeof realtimeApi.start !== 'function') {"
                "throw new Error("
                "'Jarvis Realtime API is not ready.'"
                ");"
                "}"
                "if (realtimeApi.start("
                f"{source_json}, {session_id_json}"
                ") !== true) {"
                "throw new Error("
                "'Jarvis Realtime start was rejected.'"
                ");"
                "}"
                "})()"
            )

            try:
                window.evaluate_js(script)

            except Exception as error:
                window_log(
                    "JavaScriptへのRealtime開始命令に"
                    f"失敗しました: {error}"
                )
                return False

            self._active_realtime_session_id = (
                normalized_session_id
            )

        window_log(
            "JavaScriptへRealtime開始命令を送信しました。"
            f" source={normalized_source},"
            f" session_id={normalized_session_id}"
        )
        return True

    def get_status(self):
        current_state = None

        if self.window is not None:
            current_state = get_window_rect_by_title(APP_WINDOW_TITLE)

        return {
            "window_exists": self.window is not None,
            "visible": self.is_window_visible,
            "title": APP_WINDOW_TITLE,
            "current_state": current_state,
        }

    def on_closed(self):
        save_current_window_state()

        self.is_window_visible = False
        self.is_shutting_down = True
        self.window = None

        with self._realtime_start_lock:
            session_id = self._active_realtime_session_id
            self._active_realtime_session_id = None

        if (
            session_id is not None
            and self._on_realtime_window_closed is not None
        ):
            try:
                notified = self._on_realtime_window_closed(
                    "window_closed",
                    session_id,
                )

                if notified is False:
                    window_log(
                        "Window終了時のRealtime終了通知が"
                        "受け付けられませんでした。"
                        f" session_id={session_id}"
                    )
                else:
                    window_log(
                        "Window終了時のRealtime終了通知を"
                        "送信しました。"
                        f" session_id={session_id}"
                    )

            except Exception as error:
                window_log(
                    "Window終了時のRealtime終了通知に"
                    f"失敗しました: {error}"
                )

        window_log("Jarvisウィンドウが閉じられました。")

        if self.stop_control_server_func:
            self.stop_control_server_func()
