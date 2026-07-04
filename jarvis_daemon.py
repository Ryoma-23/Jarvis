import subprocess
import time
import webbrowser
import urllib.request
import sys
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent

VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"

HOST = "127.0.0.1"
PORT = 8000

SERVER_URL = f"http://{HOST}:{PORT}"
HEALTH_CHECK_URL = SERVER_URL

LOG_DIR = BASE_DIR / "logs"
DAEMON_LOG_FILE = LOG_DIR / "jarvis_daemon.log"
UVICORN_LOG_FILE = LOG_DIR / "uvicorn.log"

CHECK_INTERVAL_SECONDS = 5
STARTUP_TIMEOUT_SECONDS = 30

LOCK_FILE = BASE_DIR / "jarvis_daemon.lock"

OPEN_BROWSER = "--no-browser" not in sys.argv


def write_log(message: str):
    LOG_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_message = f"[{timestamp}] {message}"

    print(log_message)

    with open(DAEMON_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(log_message + "\n")


def is_server_alive() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_CHECK_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def wait_until_server_ready() -> bool:
    write_log("Jarvisサーバーの起動完了を待っています。")

    start_time = time.time()

    while time.time() - start_time < STARTUP_TIMEOUT_SECONDS:
        if is_server_alive():
            write_log("Jarvisサーバーの起動を確認しました。")
            return True

        time.sleep(1)

    write_log("Jarvisサーバーの起動確認に失敗しました。")
    return False


def start_jarvis_server():
    LOG_DIR.mkdir(exist_ok=True)

    write_log("Jarvisサーバーを起動します。")

    uvicorn_log = open(UVICORN_LOG_FILE, "a", encoding="utf-8")

    process = subprocess.Popen(
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
    )

    write_log(f"Jarvisサーバープロセスを開始しました。PID: {process.pid}")

    return process


def stop_jarvis_server(process):
    if process is None:
        return

    if process.poll() is not None:
        write_log("Jarvisサーバーはすでに終了しています。")
        return

    write_log("Jarvisサーバーを停止します。")

    process.terminate()

    try:
        process.wait(timeout=10)
        write_log("Jarvisサーバーを正常に停止しました。")
    except subprocess.TimeoutExpired:
        write_log("正常停止できなかったため、強制終了します。")
        process.kill()


def open_jarvis_frontend():
    write_log("Jarvis画面を開きます。")
    webbrowser.open(SERVER_URL)


def main():
    write_log("Jarvis daemonを起動しました。")

    if is_another_daemon_running():
        write_log("別のJarvis daemonがすでに起動しているため終了します。")
        return

    create_lock_file()

    if not VENV_PYTHON.exists():
        write_log(f"仮想環境のPythonが見つかりません: {VENV_PYTHON}")
        return

    process = None

    try:
        if is_server_alive():
            write_log("Jarvisサーバーはすでに起動しています。")
            if OPEN_BROWSER:
                open_jarvis_frontend()
            else:
                write_log("ブラウザ自動起動は無効です。")
        else:
            process = start_jarvis_server()

            if wait_until_server_ready():
                if OPEN_BROWSER:
                    open_jarvis_frontend()
                else:
                    write_log("ブラウザ自動起動は無効です。")
            else:
                write_log("Jarvisサーバーが起動できなかったため終了します。")
                stop_jarvis_server(process)
                return

        write_log("Jarvisサーバーの監視を開始します。")

        while True:
            time.sleep(CHECK_INTERVAL_SECONDS)

            if process is not None and process.poll() is not None:
                write_log("Jarvisサーバーが停止しました。再起動します。")

                process = start_jarvis_server()

                if wait_until_server_ready():
                    write_log("Jarvisサーバーの再起動に成功しました。")
                else:
                    write_log("Jarvisサーバーの再起動に失敗しました。")

    except KeyboardInterrupt:
        write_log("終了指示を受け取りました。")

    finally:
        stop_jarvis_server(process)
        remove_lock_file()
        write_log("Jarvis daemonを終了しました。")


def is_another_daemon_running() -> bool:
    if not LOCK_FILE.exists():
        return False

    try:
        pid_text = LOCK_FILE.read_text(encoding="utf-8").strip()
        old_pid = int(pid_text)

        # WindowsでPIDが存在するか確認
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {old_pid}"],
            capture_output=True,
            text=True
        )

        return str(old_pid) in result.stdout

    except Exception:
        return False


def create_lock_file():
    current_pid = subprocess.os.getpid()

    LOCK_FILE.write_text(str(current_pid), encoding="utf-8")

    write_log(f"ロックファイルを作成しました。PID: {current_pid}")


def remove_lock_file():
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
        write_log("ロックファイルを削除しました。")



if __name__ == "__main__":
    main()