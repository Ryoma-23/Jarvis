import subprocess
import time
import webbrowser
import urllib.request
import pystray
from pathlib import Path
from datetime import datetime
from pystray import MenuItem as item
from PIL import Image, ImageDraw

BASE_DIR = Path(__file__).resolve().parent

HOST = "127.0.0.1"
PORT = 8000
WINDOW_CONTROL_HOST = "127.0.0.1"
WINDOW_CONTROL_PORT = 8766
WINDOW_CONTROL_URL = f"http://{WINDOW_CONTROL_HOST}:{WINDOW_CONTROL_PORT}"

SERVER_URL = f"http://{HOST}:{PORT}"
HEALTH_CHECK_URL = SERVER_URL

VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
LOG_DIR = BASE_DIR / "logs"
TRAY_LOG_FILE = LOG_DIR / "jarvis_tray.log"
UVICORN_LOG_FILE = LOG_DIR / "uvicorn.log"
JARVIS_WINDOW_SCRIPT = BASE_DIR / "jarvis_window.py"

CHECK_INTERVAL_SECONDS = 5
MAX_RESTART_ATTEMPTS = 3
RESTART_WINDOW_SECONDS = 60
RESTART_DELAY_SECONDS = 3
STABLE_RUNNING_SECONDS = 30

server_process = None
window_process = None
restart_attempts = 0
first_failure_time = None
server_started_at = None
is_shutting_down = False


def write_log(message: str):
    LOG_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"

    print(log_message)

    with open(TRAY_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(log_message + "\n")


def is_server_alive() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_CHECK_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def wait_until_server_ready(timeout_seconds=30) -> bool:
    write_log("Jarvisサーバーの起動完了を待っています。")

    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        if is_server_alive():
            write_log("Jarvisサーバーの起動を確認しました。")
            return True

        time.sleep(1)

    write_log("Jarvisサーバーの起動確認に失敗しました。")
    return False


def start_jarvis_server():
    global server_process
    global server_started_at

    if is_server_alive():
        write_log("既にポート8000でJarvisサーバーが起動しています。")
        write_log("Trayが管理していないサーバーの可能性があるため、起動を中止します。")
        write_log("古いJarvisプロセスを停止してから、start_jarvis_tray.bat を実行してください。")
        return False

    if not VENV_PYTHON.exists():
        write_log(f"仮想環境のPythonが見つかりません: {VENV_PYTHON}")
        return False

    LOG_DIR.mkdir(exist_ok=True)

    write_log("Jarvisサーバーを起動します。")

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

    write_log(f"Jarvisサーバープロセスを開始しました。PID: {server_process.pid}")

    if wait_until_server_ready():
        server_started_at = time.time()
        return True

    write_log("Jarvisサーバーの起動に失敗しました。")
    return False


def stop_jarvis_server():
    global server_process

    if server_process is None:
        write_log("管理中のJarvisサーバープロセスはありません。")
        return

    if server_process.poll() is not None:
        write_log("Jarvisサーバーはすでに終了しています。")
        server_process = None
        return

    write_log("Jarvisサーバーを停止します。")

    server_process.terminate()

    try:
        server_process.wait(timeout=10)
        write_log("Jarvisサーバーを正常に停止しました。")
    except subprocess.TimeoutExpired:
        write_log("正常停止できなかったため、強制終了します。")
        server_process.kill()

    server_process = None


def restart_jarvis_server():
    write_log("Jarvisサーバーを再起動します。")

    close_jarvis_window()

    stop_jarvis_server()

    time.sleep(2)

    start_jarvis_server()


def open_jarvis():
    show_jarvis_window()


def create_icon_image():
    image = Image.new("RGB", (64, 64), color=(0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, 63, 63), fill=(0, 90, 180))
    draw.ellipse((10, 10, 54, 54), fill=(255, 255, 255))
    draw.text((25, 22), "J", fill=(0, 90, 180))

    return image


def get_status_text():
    if is_server_alive():
        return "状態: 起動中"

    return "状態: 停止中"


def show_status(icon, menu_item):
    status = get_status_text()
    write_log(status)


def open_menu_clicked(icon, menu_item):
    show_jarvis_window()


def hide_window_menu_clicked(icon, menu_item):
    hide_jarvis_window()


def close_window_menu_clicked(icon, menu_item):
    close_jarvis_window()


def restart_menu_clicked(icon, menu_item):
    restart_jarvis_server()


def stop_server_menu_clicked(icon, menu_item):
    close_jarvis_window()
    stop_jarvis_server()


def quit_menu_clicked(icon, menu_item):
    global is_shutting_down

    write_log("Jarvis Trayを終了します。")

    is_shutting_down = True

    close_jarvis_window()
    stop_jarvis_server()

    icon.visible = False
    icon.stop()


def can_restart_server():
    if first_failure_time is None:
        return True

    elapsed_time = time.time() - first_failure_time

    if elapsed_time > RESTART_WINDOW_SECONDS:
        return True

    return restart_attempts < MAX_RESTART_ATTEMPTS


def update_restart_failure_count():
    global restart_attempts
    global first_failure_time

    current_time = time.time()

    if first_failure_time is None:
        first_failure_time = current_time
        restart_attempts = 1
        return

    elapsed_time = current_time - first_failure_time

    if elapsed_time > RESTART_WINDOW_SECONDS:
        first_failure_time = current_time
        restart_attempts = 1
        return

    restart_attempts += 1


def reset_restart_failure_count_if_stable():
    global restart_attempts
    global first_failure_time

    if server_started_at is None:
        return

    running_time = time.time() - server_started_at

    if running_time >= STABLE_RUNNING_SECONDS:
        if restart_attempts != 0:
            write_log("Jarvisサーバーが安定稼働したため、再起動失敗カウントをリセットします。")

        restart_attempts = 0
        first_failure_time = None


def monitor_server(icon):
    global server_process
    global server_started_at

    write_log("Jarvisサーバーの監視を開始します。")

    while not is_shutting_down:
        time.sleep(CHECK_INTERVAL_SECONDS)

        if server_process is None:
            continue

        if server_process.poll() is None:
            reset_restart_failure_count_if_stable()
            continue

        write_log("Jarvisサーバーが停止しました。")

        server_process = None

        update_restart_failure_count()

        write_log(f"再起動失敗カウント: {restart_attempts}/{MAX_RESTART_ATTEMPTS}")

        if not can_restart_server():
            write_log("短時間に複数回停止したため、再起動を停止します。")
            write_log("uvicorn.logを確認してください。")
            continue

        write_log(f"{RESTART_DELAY_SECONDS}秒後にJarvisサーバーを再起動します。")
        time.sleep(RESTART_DELAY_SECONDS)

        start_jarvis_server()


def show_jarvis_window():
    if not is_server_alive():
        write_log("Jarvisサーバーが起動していないため、起動します。")
        success = start_jarvis_server()

        if not success:
            write_log("Jarvisサーバーを起動できなかったため、ウィンドウを表示できません。")
            return

    if not ensure_jarvis_window_process():
        write_log("Jarvis Windowプロセスを準備できませんでした。")
        return

    if send_window_command("show"):
        write_log("Jarvisウィンドウを表示しました。")
    else:
        write_log("Jarvisウィンドウの表示に失敗しました。")


def close_jarvis_window():
    global window_process

    if is_window_control_alive():
        write_log("Jarvis Windowへ終了命令を送ります。")
        send_window_command("destroy")

        time.sleep(1)

    if window_process is None:
        write_log("管理中のJarvisウィンドウプロセスはありません。")
        return

    if window_process.poll() is not None:
        write_log("Jarvisウィンドウプロセスはすでに終了しています。")
        window_process = None
        return

    write_log("Jarvisウィンドウプロセスを終了します。")

    window_process.terminate()

    try:
        window_process.wait(timeout=5)
        write_log("Jarvisウィンドウプロセスを終了しました。")
    except subprocess.TimeoutExpired:
        write_log("Jarvisウィンドウプロセスを強制終了します。")
        window_process.kill()

    window_process = None


def close_window_menu_clicked(icon, menu_item):
    close_jarvis_window()


def quit_menu_clicked(icon, menu_item):
    global is_shutting_down

    write_log("Jarvis Trayを終了します。")

    is_shutting_down = True

    close_jarvis_window()
    stop_jarvis_server()

    icon.visible = False
    icon.stop()


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
        write_log(f"Window制御コマンド送信に失敗しました: {command} / {error}")
        return False


def ensure_jarvis_window_process():
    global window_process

    if is_window_control_alive():
        write_log("Jarvis Window制御サーバーはすでに起動しています。")
        return True

    if window_process is not None and window_process.poll() is None:
        write_log("Jarvis Windowプロセスは起動中ですが、制御サーバーがまだ応答していません。")
    else:
        if not JARVIS_WINDOW_SCRIPT.exists():
            write_log(f"Jarvisウィンドウ用スクリプトが見つかりません: {JARVIS_WINDOW_SCRIPT}")
            return False

        write_log("Jarvis Windowプロセスを起動します。")

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
            write_log("Jarvis Window制御サーバーの起動を確認しました。")
            return True

        time.sleep(0.5)

    write_log("Jarvis Window制御サーバーの起動確認に失敗しました。")
    return False


def hide_jarvis_window():
    if not is_window_control_alive():
        write_log("Jarvis Window制御サーバーが起動していません。")
        return

    if send_window_command("hide"):
        write_log("Jarvisウィンドウを非表示にしました。")
    else:
        write_log("Jarvisウィンドウの非表示に失敗しました。")



def setup_icon(icon):
    write_log("Jarvis Trayを起動しました。")

    # タスクトレイアイコンを明示的に表示する
    icon.visible = True
    write_log("Jarvis Trayアイコンを表示状態にしました。")

    import threading

    def start_server_job():
        success = start_jarvis_server()

        if success:
            write_log("Jarvisサーバーの起動に成功しました。")
        else:
            write_log("Jarvisサーバーは起動できませんでした。Trayは起動したままにします。")

    server_thread = threading.Thread(
        target=start_server_job,
        daemon=True
    )
    server_thread.start()

    monitor_thread = threading.Thread(
        target=monitor_server,
        args=(icon,),
        daemon=True
    )
    monitor_thread.start()


def main():
    write_log("Jarvis Tray mainを開始します。")

    icon_image = create_icon_image()

    menu = pystray.Menu(
        item("Jarvisを表示", open_menu_clicked),
        item("Jarvisを隠す", hide_window_menu_clicked),
        item("Jarvisウィンドウを終了", close_window_menu_clicked),
        item("状態確認", show_status),
        pystray.Menu.SEPARATOR,
        item("サーバー再起動", restart_menu_clicked),
        item("サーバー停止", stop_server_menu_clicked),
        pystray.Menu.SEPARATOR,
        item("終了", quit_menu_clicked),
    )

    icon = pystray.Icon(
        "Jarvis",
        icon_image,
        "Jarvis",
        menu
    )

    write_log("タスクトレイアイコンを起動します。")
    icon.run(setup_icon)
    write_log("タスクトレイアイコンを終了しました。")


if __name__ == "__main__":
    main()