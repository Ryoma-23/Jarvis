import json
import sys
import time
import urllib.request
import threading
import webview
import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime



HOST = "127.0.0.1"
PORT = 8000
SERVER_URL = f"http://{HOST}:{PORT}"

CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 8766
CONTROL_URL = f"http://{CONTROL_HOST}:{CONTROL_PORT}"

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
WINDOW_LOG_FILE = LOG_DIR / "jarvis_window.log"
APP_WINDOW_TITLE = "J.A.R.V.I.S"

window = None
control_server = None
is_shutting_down = False
is_window_visible = False


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
    global is_window_visible

    if window is None:
        write_log("show命令を受け取りましたが、windowが存在しません。")
        return False

    write_log("Jarvisウィンドウを表示・復帰します。")

    try:
        window.show()
        window.restore()

        # pywebview側の表示処理が反映されるまで少し待つ
        time.sleep(0.2)

        bring_window_to_front_by_title(APP_WINDOW_TITLE)

        is_window_visible = True

        return True

    except Exception as error:
        write_log(f"Jarvisウィンドウの表示・復帰に失敗しました: {error}")
        return False


def hide_window():
    global window
    global is_window_visible

    if window is None:
        write_log("hide命令を受け取りましたが、windowが存在しません。")
        return False

    try:
        write_log("Jarvisウィンドウを非表示にします。")
        window.hide()

        is_window_visible = False

        return True

    except Exception as error:
        write_log(f"Jarvisウィンドウの非表示に失敗しました: {error}")
        return False


def destroy_window():
    global window
    global is_shutting_down
    global is_window_visible

    is_shutting_down = True

    if window is None:
        write_log("destroy命令を受け取りましたが、windowが存在しません。")
        return False

    try:
        write_log("Jarvisウィンドウを終了します。")
        is_window_visible = False
        window.destroy()

        return True

    except Exception as error:
        write_log(f"Jarvisウィンドウ終了に失敗しました: {error}")
        return False


class ControlRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            json_response(self, 200, {
                "ok": True,
                "message": "Jarvis Window control server is running"
            })
            return
        
        if self.path == "/status":
            json_response(self, 200, {
                "ok": True,
                "window_exists": window is not None,
                "visible": is_window_visible,
                "title": APP_WINDOW_TITLE
            })
            return

        if self.path == "/show":
            success = show_window()
            json_response(self, 200 if success else 500, {
                "ok": success,
                "action": "show"
            })
            return
        
        if self.path == "/focus":
            success = focus_window()
            json_response(self, 200 if success else 500, {
                "ok": success,
                "action": "focus"
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
    global is_window_visible

    is_window_visible = False

    write_log("Jarvisウィンドウが閉じられました。")
    stop_control_server()


def bring_window_to_front_by_title(title: str) -> bool:
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.FindWindowW(None, title)

        if not hwnd:
            write_log(f"前面表示対象のウィンドウが見つかりません: {title}")
            return False

        SW_RESTORE = 9
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2

        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040

        # 現在前面にあるウィンドウ
        foreground_hwnd = user32.GetForegroundWindow()

        # 現在スレッドID
        current_thread_id = kernel32.GetCurrentThreadId()

        # 前面ウィンドウのスレッドID
        foreground_thread_id = user32.GetWindowThreadProcessId(
            foreground_hwnd,
            None
        )

        # 対象ウィンドウのスレッドID
        target_thread_id = user32.GetWindowThreadProcessId(
            hwnd,
            None
        )

        # 最小化されていれば復元
        user32.ShowWindow(hwnd, SW_RESTORE)

        # スレッド入力を一時的に接続する
        user32.AttachThreadInput(
            foreground_thread_id,
            current_thread_id,
            True
        )

        user32.AttachThreadInput(
            target_thread_id,
            current_thread_id,
            True
        )

        # 一瞬だけ最前面にする
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        )

        # 通常ウィンドウに戻す
        user32.SetWindowPos(
            hwnd,
            HWND_NOTOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        )

        # フォーカスを当てる
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
        user32.BringWindowToTop(hwnd)

        # スレッド入力の接続を解除する
        user32.AttachThreadInput(
            foreground_thread_id,
            current_thread_id,
            False
        )

        user32.AttachThreadInput(
            target_thread_id,
            current_thread_id,
            False
        )

        write_log("Windows APIでJarvisウィンドウを前面に表示しました。")
        return True

    except Exception as error:
        write_log(f"Windows APIでの前面表示に失敗しました: {error}")
        return False


def focus_window():
    global window

    if window is None:
        write_log("focus命令を受け取りましたが、windowが存在しません。")
        return False

    write_log("Jarvisウィンドウを前面に出します。")

    try:
        return bring_window_to_front_by_title(APP_WINDOW_TITLE)

    except Exception as error:
        write_log(f"Jarvisウィンドウの前面表示に失敗しました: {error}")
        return False


def start_window_hidden():
    global window

    if not is_server_alive():
        write_log("Jarvisサーバーが起動していません。")
        sys.exit(1)

    window = webview.create_window(
        title=APP_WINDOW_TITLE,
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