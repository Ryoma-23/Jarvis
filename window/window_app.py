import sys
import threading
import urllib.request

import webview

from core.config import APP_WINDOW_TITLE, SERVER_URL, WEBVIEW_DATA_DIR
from core.logger import window_log
from window.control_server import WindowControlServer
from window.window_controller import WindowController
from window.window_state import load_window_state


def is_server_alive() -> bool:
    try:
        with urllib.request.urlopen(SERVER_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def run_window_app():
    if not is_server_alive():
        window_log("Jarvisサーバーが起動していません。")
        sys.exit(1)

    controller = WindowController()
    control_server = WindowControlServer(controller)

    controller.set_stop_control_server_func(control_server.stop)

    window_state = load_window_state()

    window = webview.create_window(
        title=APP_WINDOW_TITLE,
        url=SERVER_URL,
        x=window_state["x"],
        y=window_state["y"],
        width=window_state["width"],
        height=window_state["height"],
        resizable=True,
        fullscreen=False,
        confirm_close=False,
        hidden=True,
    )

    controller.set_window(window)

    window.events.closed += controller.on_closed

    control_thread = threading.Thread(
        target=control_server.start,
        daemon=True
    )
    control_thread.start()

    window_log("Jarvisウィンドウを非表示状態で起動します。")

    WEBVIEW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    webview.start(storage_path=str(WEBVIEW_DATA_DIR))