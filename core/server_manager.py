import subprocess
import time
import urllib.request

from core.config import (
    BASE_DIR,
    VENV_PYTHON,
    HOST,
    PORT,
    HEALTH_CHECK_URL,
    LOG_DIR,
    UVICORN_LOG_FILE,
)
from core.logger import tray_log


server_process = None
server_started_at = None


def is_server_alive() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_CHECK_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def wait_until_server_ready(timeout_seconds=30) -> bool:
    tray_log("Jarvisサーバーの起動完了を待っています。")

    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        if is_server_alive():
            tray_log("Jarvisサーバーの起動を確認しました。")
            return True

        time.sleep(1)

    tray_log("Jarvisサーバーの起動確認に失敗しました。")
    return False


def start_jarvis_server():
    global server_process
    global server_started_at

    if is_server_alive():
        tray_log("既にポート8000でJarvisサーバーが起動しています。")
        tray_log("Trayが管理していないサーバーの可能性があるため、起動を中止します。")
        tray_log("古いJarvisプロセスを停止してから、start_jarvis_tray.bat を実行してください。")
        return False

    if not VENV_PYTHON.exists():
        tray_log(f"仮想環境のPythonが見つかりません: {VENV_PYTHON}")
        return False

    LOG_DIR.mkdir(exist_ok=True)

    tray_log("Jarvisサーバーを起動します。")

    uvicorn_log = open(UVICORN_LOG_FILE, "a", encoding="utf-8")

    server_process = subprocess.Popen(
        [
            str(VENV_PYTHON),
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        cwd=BASE_DIR,
        stdout=uvicorn_log,
        stderr=uvicorn_log,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    tray_log(f"Jarvisサーバープロセスを開始しました。PID: {server_process.pid}")

    if wait_until_server_ready():
        server_started_at = time.time()
        return True

    tray_log("Jarvisサーバーの起動に失敗しました。")
    return False


def stop_jarvis_server():
    global server_process

    if server_process is None:
        tray_log("管理中のJarvisサーバープロセスはありません。")
        return

    if server_process.poll() is not None:
        tray_log("Jarvisサーバーはすでに終了しています。")
        server_process = None
        return

    tray_log("Jarvisサーバーを停止します。")

    server_process.terminate()

    try:
        server_process.wait(timeout=10)
        tray_log("Jarvisサーバーを正常に停止しました。")
    except subprocess.TimeoutExpired:
        tray_log("正常停止できなかったため、強制終了します。")
        server_process.kill()

    server_process = None


def get_status_text():
    if is_server_alive():
        return "状態: 起動中"

    return "状態: 停止中"


def get_server_process():
    return server_process


def set_server_process_none():
    global server_process
    server_process = None


def get_server_started_at():
    return server_started_at