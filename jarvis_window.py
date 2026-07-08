import json
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime
import threading

import webview


HOST = "127.0.0.1"
PORT = 8000
SERVER_URL = f"http://{HOST}:{PORT}"

CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 8766
CONTROL_URL = f"http://{CONTROL_HOST}:{CONTROL_PORT}"

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
WINDOW_LOG_FILE = LOG_DIR / "jarvis_window.log"

window = None
control_server = None
is_shutting_down = False


def write_log(message: str):
    LOG_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"

    print(log_message)

    with open(WINDOW_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(log_message + "\n")


def is_server_alive() -> bool:
    try:
        with urllib.request.urlopen(SERVER_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def json_response(handler, status_code, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def show_window():
    global window

    if window is None:
        write_log("show命令を受け取りましたが、windowが存在しません。")
        return False

    write_log("Jarvisウィンドウを表示します。")
    window.show()
    window.restore()

    return True


def hide_window():
    global window

    if window is None:
        write_log("hide命令を受け取りましたが、windowが存在しません。")
        return False

    write_log("Jarvisウィンドウを非表示にします。")
    window.hide()

    return True


def destroy_window():
    global window
    global is_shutting_down

    is_shutting_down = True

    if window is None:
        write_log("destroy命令を受け取りましたが、windowが存在しません。")
        return False

    write_log("Jarvisウィンドウを終了します。")
    window.destroy()

    return True


class ControlRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            json_response(self, 200, {
                "ok": True,
                "message": "Jarvis Window control server is running"
            })
            return

        if self.path == "/show":
            success = show_window()
            json_response(self, 200 if success else 500, {
                "ok": success,
                "action": "show"
            })
            return

        if self.path == "/hide":
            success = hide_window()
            json_response(self, 200 if success else 500, {
                "ok": success,
                "action": "hide"
            })
            return

        if self.path == "/destroy":
            success = destroy_window()
            json_response(self, 200 if success else 500, {
                "ok": success,
                "action": "destroy"
            })
            return

        json_response(self, 404, {
            "ok": False,
            "message": "Not found"
        })

    def log_message(self, format, *args):
        # 標準出力へのHTTPログを抑制する
        return


def start_control_server():
    global control_server

    write_log(f"Window制御サーバーを起動します: {CONTROL_URL}")

    control_server = ThreadingHTTPServer(
        (CONTROL_HOST, CONTROL_PORT),
        ControlRequestHandler
    )

    control_server.serve_forever()


def stop_control_server():
    global control_server

    if control_server is None:
        return

    write_log("Window制御サーバーを停止します。")
    control_server.shutdown()
    control_server.server_close()
    control_server = None


def on_closed():
    write_log("Jarvisウィンドウが閉じられました。")
    stop_control_server()


def start_window_hidden():
    global window

    if not is_server_alive():
        write_log("Jarvisサーバーが起動していません。")
        sys.exit(1)

    window = webview.create_window(
        title="J.A.R.V.I.S",
        url=SERVER_URL,
        width=1100,
        height=850,
        resizable=True,
        fullscreen=False,
        confirm_close=False,
        hidden=True,
    )

    window.events.closed += on_closed

    control_thread = threading.Thread(
        target=start_control_server,
        daemon=True
    )
    control_thread.start()

    write_log("Jarvisウィンドウを非表示状態で起動します。")

    webview.start()


if __name__ == "__main__":
    start_window_hidden()