import sys
import time
import webbrowser

from core.config import SERVER_URL, VENV_PYTHON, CHECK_INTERVAL_SECONDS, RESTART_DELAY_SECONDS
from core.logger import daemon_log
from core.process_lock import ProcessLock
from core.restart_policy import RestartPolicy
from core.server_manager import ServerManager


def run_daemon_app():
    open_browser = "--no-browser" not in sys.argv

    daemon_log("Jarvis daemonを起動しました。")

    lock = ProcessLock(daemon_log)

    if lock.is_another_running():
        daemon_log("別のJarvis daemonがすでに起動しているため終了します。")
        return

    lock.create()

    server = ServerManager(log_func=daemon_log, hide_console=False)
    restart_policy = RestartPolicy(log_func=daemon_log)

    if not VENV_PYTHON.exists():
        daemon_log(f"仮想環境のPythonが見つかりません: {VENV_PYTHON}")
        lock.remove()
        return

    try:
        if server.is_alive():
            daemon_log("既にポート8000でサーバーが起動しています。")
            daemon_log("daemon管理外のサーバーの可能性があるため、今回は起動せず終了します。")
            return

        if not server.start():
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

            if server.process is not None and server.process.poll() is None:
                restart_policy.reset_if_stable(server.started_at)
                continue

            daemon_log("Jarvisサーバーが停止しました。")

            restart_policy.record_failure()
            daemon_log(restart_policy.get_attempt_text())

            if not restart_policy.can_restart():
                daemon_log("短時間に複数回停止したため、再起動を停止します。")
                daemon_log("uvicorn.logを確認してください。")
                break

            daemon_log(f"{RESTART_DELAY_SECONDS}秒後にJarvisサーバーを再起動します。")
            time.sleep(RESTART_DELAY_SECONDS)

            if server.start():
                daemon_log("Jarvisサーバーの再起動に成功しました。")
            else:
                daemon_log("Jarvisサーバーの再起動に失敗しました。")

    except KeyboardInterrupt:
        daemon_log("終了指示を受け取りました。")

    finally:
        server.stop()
        lock.remove()
        daemon_log("Jarvis daemonを終了しました。")