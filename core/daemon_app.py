import sys
import time
import webbrowser

from core.config import (
    SERVER_URL,
    VENV_PYTHON,
    CHECK_INTERVAL_SECONDS,
    RESTART_DELAY_SECONDS,
)
from core.logger import daemon_log
from core.process_lock import (
    is_another_daemon_running,
    create_lock_file,
    remove_lock_file,
)
from core.restart_policy import (
    can_restart_server,
    update_restart_failure_count,
    reset_restart_failure_count_if_stable,
    get_restart_attempt_text,
)
from core.server_manager import (
    is_server_alive,
    start_jarvis_server,
    stop_jarvis_server,
    get_server_process,
    set_server_process_none,
    get_server_started_at,
)


def run_daemon_app():
    open_browser = "--no-browser" not in sys.argv

    daemon_log("Jarvis daemonを起動しました。")

    if is_another_daemon_running():
        daemon_log("別のJarvis daemonがすでに起動しているため終了します。")
        return

    create_lock_file(daemon_log)

    if not VENV_PYTHON.exists():
        daemon_log(f"仮想環境のPythonが見つかりません: {VENV_PYTHON}")
        remove_lock_file(daemon_log)
        return

    try:
        if is_server_alive():
            daemon_log("既にポート8000でサーバーが起動しています。")
            daemon_log("daemon管理外のサーバーの可能性があるため、今回は起動せず終了します。")
            return

        if not start_jarvis_server():
            daemon_log("Jarvisサーバーが起動できなかったため終了します。")
            return

        if open_browser:
            daemon_log("Jarvis画面を開きます。")
            webbrowser.open(SERVER_URL)
        else:
            daemon_log("ブラウザ自動起動は無効です。")

        daemon_log("Jarvisサーバーの監視を開始します。")

        while True:
            time.sleep(CHECK_INTERVAL_SECONDS)

            process = get_server_process()

            if process is not None and process.poll() is None:
                reset_restart_failure_count_if_stable(get_server_started_at())
                continue

            daemon_log("Jarvisサーバーが停止しました。")

            set_server_process_none()

            update_restart_failure_count()
            daemon_log(get_restart_attempt_text())

            if not can_restart_server():
                daemon_log("短時間に複数回停止したため、再起動を停止します。")
                daemon_log("uvicorn.logを確認してください。")
                break

            daemon_log(f"{RESTART_DELAY_SECONDS}秒後にJarvisサーバーを再起動します。")
            time.sleep(RESTART_DELAY_SECONDS)

            if start_jarvis_server():
                daemon_log("Jarvisサーバーの再起動に成功しました。")
            else:
                daemon_log("Jarvisサーバーの再起動に失敗しました。")

    except KeyboardInterrupt:
        daemon_log("終了指示を受け取りました。")

    finally:
        stop_jarvis_server()
        remove_lock_file(daemon_log)
        daemon_log("Jarvis daemonを終了しました。")