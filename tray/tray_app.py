import threading
import time

import pystray
from pystray import MenuItem as item

from core.config import CHECK_INTERVAL_SECONDS, RESTART_DELAY_SECONDS
from core.logger import tray_log
from core.server_manager import (
    is_server_alive,
    start_jarvis_server,
    stop_jarvis_server,
    get_status_text,
    get_server_process,
    set_server_process_none,
    get_server_started_at,
)
from core.restart_policy import (
    can_restart_server,
    update_restart_failure_count,
    reset_restart_failure_count_if_stable,
    get_restart_attempt_text,
)
from tray.tray_icon import create_icon_image
from tray.window_client import (
    show_jarvis_window as show_window_from_client,
    hide_jarvis_window,
    close_jarvis_window,
    get_window_status,
)


class TrayApp:
    def __init__(self):
        self.is_shutting_down = False

    def show_jarvis_window(self):
        show_window_from_client(is_server_alive, start_jarvis_server)

    def restart_jarvis_server(self):
        tray_log("Jarvisサーバーを再起動します。")

        close_jarvis_window()

        stop_jarvis_server()

        time.sleep(2)

        start_jarvis_server()

    def show_status(self, icon, menu_item):
        server_status = get_status_text()
        tray_log(server_status)

        window_status = get_window_status()

        if window_status:
            tray_log(f"Window状態: {window_status}")
        else:
            tray_log("Window状態: 取得できません")

    def open_menu_clicked(self, icon, menu_item):
        self.show_jarvis_window()

    def hide_window_menu_clicked(self, icon, menu_item):
        hide_jarvis_window()

    def close_window_menu_clicked(self, icon, menu_item):
        close_jarvis_window()

    def restart_menu_clicked(self, icon, menu_item):
        self.restart_jarvis_server()

    def stop_server_menu_clicked(self, icon, menu_item):
        close_jarvis_window()
        stop_jarvis_server()

    def quit_menu_clicked(self, icon, menu_item):
        tray_log("Jarvis Trayを終了します。")

        self.is_shutting_down = True

        close_jarvis_window()
        stop_jarvis_server()

        icon.visible = False
        icon.stop()

    def monitor_server(self):
        tray_log("Jarvisサーバーの監視を開始します。")

        while not self.is_shutting_down:
            time.sleep(CHECK_INTERVAL_SECONDS)

            process = get_server_process()

            if process is None:
                continue

            if process.poll() is None:
                reset_restart_failure_count_if_stable(get_server_started_at())
                continue

            tray_log("Jarvisサーバーが停止しました。")

            set_server_process_none()

            update_restart_failure_count()

            tray_log(get_restart_attempt_text())

            if not can_restart_server():
                tray_log("短時間に複数回停止したため、再起動を停止します。")
                tray_log("uvicorn.logを確認してください。")
                continue

            tray_log(f"{RESTART_DELAY_SECONDS}秒後にJarvisサーバーを再起動します。")
            time.sleep(RESTART_DELAY_SECONDS)

            start_jarvis_server()

    def setup_icon(self, icon):
        tray_log("Jarvis Trayを起動しました。")

        icon.visible = True
        tray_log("Jarvis Trayアイコンを表示状態にしました。")

        def start_server_job():
            success = start_jarvis_server()

            if success:
                tray_log("Jarvisサーバーの起動に成功しました。")
            else:
                tray_log("Jarvisサーバーは起動できませんでした。Trayは起動したままにします。")

        server_thread = threading.Thread(
            target=start_server_job,
            daemon=True,
        )
        server_thread.start()

        monitor_thread = threading.Thread(
            target=self.monitor_server,
            daemon=True,
        )
        monitor_thread.start()

    def run(self):
        tray_log("Jarvis Tray mainを開始します。")

        menu = pystray.Menu(
            item("Jarvisを表示", self.open_menu_clicked),
            item("Jarvisを隠す", self.hide_window_menu_clicked),
            item("Jarvisウィンドウを終了", self.close_window_menu_clicked),
            item("状態確認", self.show_status),
            pystray.Menu.SEPARATOR,
            item("サーバー再起動", self.restart_menu_clicked),
            item("サーバー停止", self.stop_server_menu_clicked),
            pystray.Menu.SEPARATOR,
            item("終了", self.quit_menu_clicked),
        )

        icon = pystray.Icon(
            "Jarvis",
            create_icon_image(),
            "Jarvis",
            menu,
        )

        tray_log("タスクトレイアイコンを起動します。")
        icon.run(self.setup_icon)
        tray_log("タスクトレイアイコンを終了しました。")


def run_tray_app():
    app = TrayApp()
    app.run()