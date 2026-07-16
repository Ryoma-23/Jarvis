import subprocess
import os

from core.config import LOCK_FILE


class ProcessLock:
    def __init__(self, log_func):
        self.log = log_func

    def is_another_running(self) -> bool:
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

    def create(self):
        current_pid = os.getpid()
        LOCK_FILE.write_text(str(current_pid), encoding="utf-8")
        self.log(f"ロックファイルを作成しました。PID: {current_pid}")

    def remove(self):
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
            self.log("ロックファイルを削除しました。")