from core.config import APP_WINDOW_TITLE
from core.logger import window_log
from window.window_state import save_current_window_state
from window.windows_api import (
    bring_window_to_front_by_title,
    get_window_rect_by_title,
)


class WindowController:
    def __init__(self):
        self.window = None
        self.is_window_visible = False
        self.is_shutting_down = False
        self.stop_control_server_func = None

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

        window_log("Jarvisウィンドウが閉じられました。")

        if self.stop_control_server_func:
            self.stop_control_server_func()