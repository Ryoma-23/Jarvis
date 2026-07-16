from datetime import datetime

from core.config import DAEMON_LOG_FILE, TRAY_LOG_FILE, WINDOW_LOG_FILE


def write_log(log_file, message: str):
    log_file.parent.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"

    print(log_message)

    with open(log_file, "a", encoding="utf-8") as file:
        file.write(log_message + "\n")


def daemon_log(message: str):
    write_log(DAEMON_LOG_FILE, message)


def tray_log(message: str):
    write_log(TRAY_LOG_FILE, message)


def window_log(message: str):
    write_log(WINDOW_LOG_FILE, message)


def tray_log(message: str):
    TRAY_LOG_FILE.parent.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"

    print(log_message)

    with open(TRAY_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(log_message + "\n")