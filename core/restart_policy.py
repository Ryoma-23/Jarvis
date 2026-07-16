import time

from core.config import (
    MAX_RESTART_ATTEMPTS,
    RESTART_WINDOW_SECONDS,
    STABLE_RUNNING_SECONDS,
)
from core.logger import tray_log


restart_attempts = 0
first_failure_time = None


def can_restart_server() -> bool:
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


def reset_restart_failure_count_if_stable(server_started_at):
    global restart_attempts
    global first_failure_time

    if server_started_at is None:
        return

    running_time = time.time() - server_started_at

    if running_time >= STABLE_RUNNING_SECONDS:
        if restart_attempts != 0:
            tray_log("Jarvisサーバーが安定稼働したため、再起動失敗カウントをリセットします。")

        restart_attempts = 0
        first_failure_time = None


def get_restart_attempt_text() -> str:
    return f"再起動失敗カウント: {restart_attempts}/{MAX_RESTART_ATTEMPTS}"