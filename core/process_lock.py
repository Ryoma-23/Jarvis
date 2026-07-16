import os
import subprocess

from core.config import LOCK_FILE


def is_another_daemon_running() -> bool:
    if not LOCK_FILE.exists():
        return False

    try:
        pid_text = LOCK_FILE.read_text(encoding="utf-8").strip()
        old_pid = int(pid_text)

        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {old_pid}"],
            capture_output=True,
            text=True,
        )

        return str(old_pid) in result.stdout

    except Exception:
        return False


def create_lock_file(log_func):
    current_pid = os.getpid()

    LOCK_FILE.write_text(str(current_pid), encoding="utf-8")

    log_func(f"ロックファイルを作成しました。PID: {current_pid}")


def remove_lock_file(log_func):
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
        log_func("ロックファイルを削除しました。")