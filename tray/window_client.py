import subprocess
import time
import urllib.request

from core.config import (
    BASE_DIR,
    VENV_PYTHON,
    JARVIS_WINDOW_SCRIPT,
    WINDOW_CONTROL_URL,
)
from core.logger import tray_log


window_process = None


def is_window_control_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{WINDOW_CONTROL_URL}/health", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def send_window_command(command: str) -> bool:
    try:
        with urllib.request.urlopen(f"{WINDOW_CONTROL_URL}/{command}", timeout=2) as response:
            return response.status == 200
    except Exception as error:
        tray_log(f"Window制御コマンド送信に失敗しました: {command} / {error}")
        return False


def get_window_status():
    if not is_window_control_alive():
        return "未起動"

    try:
        with urllib.request.urlopen(f"{WINDOW_CONTROL_URL}/status", timeout=2) as response:
            data = response.read().decode("utf-8")
            return data
    except Exception as error:
        tray_log(f"Window状態取得に失敗しました: {error}")
        return None


def ensure_jarvis_window_process():
    global window_process

    if is_window_control_alive():
        tray_log("Jarvis Window制御サーバーはすでに起動しています。")
        return True

    if window_process is not None and window_process.poll() is None:
        tray_log("Jarvis Windowプロセスは起動中ですが、制御サーバーがまだ応答していません。")
    else:
        if not JARVIS_WINDOW_SCRIPT.exists():
            tray_log(f"Jarvisウィンドウ用スクリプトが見つかりません: {JARVIS_WINDOW_SCRIPT}")
            return False

        tray_log("Jarvis Windowプロセスを起動します。")

        window_process = subprocess.Popen(
            [
                str(VENV_PYTHON),
                str(JARVIS_WINDOW_SCRIPT),
            ],
            cwd=BASE_DIR,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    start_time = time.time()

    while time.time() - start_time < 10:
        if is_window_control_alive():
            tray_log("Jarvis Window制御サーバーの起動を確認しました。")
            return True

        time.sleep(0.5)

    tray_log("Jarvis Window制御サーバーの起動確認に失敗しました。")
    return False


def close_jarvis_window():
    global window_process

    if is_window_control_alive():
        tray_log("Jarvis Windowへ終了命令を送ります。")
        send_window_command("destroy")

        time.sleep(1)

    if window_process is None:
        tray_log("管理中のJarvisウィンドウプロセスはありません。")
        return

    if window_process.poll() is not None:
        tray_log("Jarvisウィンドウプロセスの終了を確認しました。")
        window_process = None
        return

    tray_log("Jarvisウィンドウプロセスを終了します。")

    window_process.terminate()

    try:
        window_process.wait(timeout=5)
        tray_log("Jarvisウィンドウプロセスを終了しました。")
    except subprocess.TimeoutExpired:
        tray_log("Jarvisウィンドウプロセスを強制終了します。")
        window_process.kill()

    window_process = None


def hide_jarvis_window():
    if not is_window_control_alive():
        tray_log("Jarvis Window制御サーバーが起動していません。")
        return

    if send_window_command("hide"):
        tray_log("Jarvisウィンドウを非表示にしました。")
    else:
        tray_log("Jarvisウィンドウの非表示に失敗しました。")


def show_jarvis_window(is_server_alive_func, start_server_func):
    if not is_server_alive_func():
        tray_log("Jarvisサーバーが起動していないため、起動します。")
        success = start_server_func()

        if not success:
            tray_log("Jarvisサーバーを起動できなかったため、ウィンドウを表示できません。")
            return

    if not ensure_jarvis_window_process():
        tray_log("Jarvis Windowプロセスを準備できませんでした。")
        return

    if send_window_command("show"):
        tray_log("Jarvisウィンドウを表示しました。")
    else:
        tray_log("Jarvisウィンドウの表示に失敗しました。")