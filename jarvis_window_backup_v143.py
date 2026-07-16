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
DATA_DIR = BASE_DIR / "data"
WINDOW_STATE_FILE = DATA_DIR / "window_state.json"
WINDOW_LOG_FILE = LOG_DIR / "jarvis_window.log"
APP_WINDOW_TITLE = "J.A.R.V.I.S"
DEFAULT_WINDOW_STATE = {
  "x": 0,
  "y": 0,
  "width": 974,
  "height": 1039
}

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

        save_current_window_state()

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

        save_current_window_state()

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
            current_state = None

            if window is not None:
                current_state = get_window_rect_by_title(APP_WINDOW_TITLE)

            json_response(self, 200, {
                "ok": True,
                "window_exists": window is not None,
                "visible": is_window_visible,
                "title": APP_WINDOW_TITLE,
                "current_state": current_state
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
        
        if self.path == "/save-state":
            success = save_current_window_state()
            json_response(self, 200 if success else 500, {
                "ok": success,
                "action": "save-state"
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

    save_current_window_state()

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


def load_window_state():
    DATA_DIR.mkdir(exist_ok=True)

    if not WINDOW_STATE_FILE.exists():
        write_log("window_state.json が存在しないため、初期値を使用します。")
        return get_safe_default_window_state()

    try:
        with open(WINDOW_STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)

        x = int(state.get("x", DEFAULT_WINDOW_STATE["x"]))
        y = int(state.get("y", DEFAULT_WINDOW_STATE["y"]))
        width = int(state.get("width", DEFAULT_WINDOW_STATE["width"]))
        height = int(state.get("height", DEFAULT_WINDOW_STATE["height"]))

        if width < 400:
            width = DEFAULT_WINDOW_STATE["width"]

        if height < 300:
            height = DEFAULT_WINDOW_STATE["height"]

        loaded_state = {
            "x": x,
            "y": y,
            "width": width,
            "height": height
        }

        loaded_state = clamp_window_size_to_screen(loaded_state)

        write_log(f"ウィンドウ状態を読み込みました: {loaded_state}")

        if not is_window_state_visible_on_screen(loaded_state):
            safe_state = get_safe_default_window_state()
            save_window_state(safe_state)
            return safe_state

        return loaded_state

    except Exception as error:
        write_log(f"ウィンドウ状態の読み込みに失敗しました。初期値を使用します: {error}")
        return get_safe_default_window_state()


def save_window_state(state):
    DATA_DIR.mkdir(exist_ok=True)

    try:
        temp_file = WINDOW_STATE_FILE.with_suffix(".json.tmp")

        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)

        temp_file.replace(WINDOW_STATE_FILE)

        write_log(f"ウィンドウ状態を保存しました: {state}")

        return True

    except Exception as error:
        write_log(f"ウィンドウ状態の保存に失敗しました: {error}")
        return False


def get_window_rect_by_title(title: str):
    try:
        user32 = ctypes.windll.user32

        hwnd = user32.FindWindowW(None, title)

        if not hwnd:
            write_log(f"位置取得対象のウィンドウが見つかりません: {title}")
            return None

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()

        success = user32.GetWindowRect(hwnd, ctypes.byref(rect))

        if not success:
            write_log("GetWindowRect に失敗しました。")
            return None

        x = rect.left
        y = rect.top
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        state = {
            "x": x,
            "y": y,
            "width": width,
            "height": height
        }

        write_log(f"現在のウィンドウ状態を取得しました: {state}")

        return state

    except Exception as error:
        write_log(f"Windows APIでのウィンドウ状態取得に失敗しました: {error}")
        return None


def save_current_window_state():
    state = get_window_rect_by_title(APP_WINDOW_TITLE)

    if state is None:
        write_log("現在のウィンドウ状態を取得できなかったため、保存しません。")
        return False

    return save_window_state(state)


def get_virtual_screen_rect():
    try:
        user32 = ctypes.windll.user32

        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        SM_CXVIRTUALSCREEN = 78
        SM_CYVIRTUALSCREEN = 79

        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        rect = {
            "left": x,
            "top": y,
            "right": x + width,
            "bottom": y + height,
            "width": width,
            "height": height
        }

        write_log(f"現在の仮想画面範囲を取得しました: {rect}")

        return rect

    except Exception as error:
        write_log(f"仮想画面範囲の取得に失敗しました: {error}")
        return None


def is_window_state_visible_on_screen(state):
    screen_rect = get_virtual_screen_rect()

    if screen_rect is None:
        write_log("画面範囲を取得できないため、保存位置を有効として扱います。")
        return True

    x = state["x"]
    y = state["y"]
    width = state["width"]
    height = state["height"]

    window_left = x
    window_top = y
    window_right = x + width
    window_bottom = y + height

    visible_margin = 100

    is_visible_horizontally = (
        window_right > screen_rect["left"] + visible_margin and
        window_left < screen_rect["right"] - visible_margin
    )

    is_visible_vertically = (
        window_bottom > screen_rect["top"] + visible_margin and
        window_top < screen_rect["bottom"] - visible_margin
    )

    is_visible = is_visible_horizontally and is_visible_vertically

    if is_visible:
        write_log("保存されたウィンドウ位置は現在の画面範囲内です。")
    else:
        write_log("保存されたウィンドウ位置が画面外のため、初期位置に戻します。")
        write_log(f"保存位置: {state}")
        write_log(f"画面範囲: {screen_rect}")

    return is_visible


def get_safe_default_window_state():
    screen_rect = get_virtual_screen_rect()

    if screen_rect is None:
        return DEFAULT_WINDOW_STATE.copy()

    width = DEFAULT_WINDOW_STATE["width"]
    height = DEFAULT_WINDOW_STATE["height"]

    screen_width = screen_rect["width"]
    screen_height = screen_rect["height"]

    if width > screen_width:
        width = max(800, screen_width - 100)

    if height > screen_height:
        height = max(600, screen_height - 100)

    safe_state = {
        "x": 0,
        "y": 0,
        "width": width,
        "height": height
    }

    write_log(f"安全な初期ウィンドウ状態を使用します: {safe_state}")

    return safe_state


def clamp_window_size_to_screen(state):
    screen_rect = get_virtual_screen_rect()

    if screen_rect is None:
        return state

    max_width = max(800, screen_rect["width"] - 100)
    max_height = max(600, screen_rect["height"] - 100)

    if state["width"] > max_width:
        write_log(f"ウィンドウ幅が大きすぎるため補正します: {state['width']} -> {max_width}")
        state["width"] = max_width

    if state["height"] > max_height:
        write_log(f"ウィンドウ高さが大きすぎるため補正します: {state['height']} -> {max_height}")
        state["height"] = max_height

    return state



def start_window_hidden():
    global window

    if not is_server_alive():
        write_log("Jarvisサーバーが起動していません。")
        sys.exit(1)

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