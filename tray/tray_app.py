import threading
import time

import pystray
from pystray import MenuItem as item

from core.config import (
    CHECK_INTERVAL_SECONDS,
    REALTIME_LIFECYCLE_MONITOR_INTERVAL_SECONDS,
    RESTART_DELAY_SECONDS,
    WAKEWORD_REALTIME_START_CONFIRM_TIMEOUT_SECONDS,
)
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
from tray.realtime_bridge import TrayRealtimeBridge
from tray.tray_icon import create_icon_image
from tray.window_client import (
    show_jarvis_window as show_window_from_client,
    hide_jarvis_window,
    close_jarvis_window,
    get_window_status,
    reap_exited_window_process,
    start_realtime_voice,
)
from wakeword.wakeword_manager import (
    WakeWordManager,
    WakeWordState,
)


class TrayApp:
    def __init__(self):
        self.is_shutting_down = False
        self.wakeword_manager = WakeWordManager(
            on_activate_jarvis=self.on_wakeword_detected,
        )
        self.realtime_bridge = TrayRealtimeBridge(
            on_starting=self.on_realtime_starting,
            on_started=self.on_realtime_started,
            on_finished=self.on_realtime_finished,
        )
        self._window_exit_recovery_session_id = None

    def show_jarvis_window(self) -> bool:
        return show_window_from_client(
            is_server_alive,
            start_jarvis_server,
        )

    def on_wakeword_detected(
        self,
        session_id: str,
    ) -> bool:
        """
        Wake Wordを検知したときにJarvis Windowを表示する。
        """

        if self.is_shutting_down:
            tray_log(
                "終了処理中のためWake Word起動を無視します。"
            )
            return False

        tray_log(
            "Wake Wordを検知しました。Jarvisを表示します。"
        )

        try:
            if not self.show_jarvis_window():
                return False

            if not self.realtime_bridge.is_running:
                tray_log(
                    "Realtime通知Bridgeが停止しているため"
                    "自動接続を開始できません。"
                )
                return False

            if not start_realtime_voice(
                source="wakeword",
                session_id=session_id,
            ):
                tray_log(
                    "Wake WordからのRealtime開始命令が"
                    "失敗または拒否されました。"
                    f" session_id={session_id}"
                )

                # HTTP応答だけが失われ、JavaScript側では
                # 開始済みの可能性があるため状態遷移を確認する。
                if self._wait_for_realtime_start(
                    session_id,
                ):
                    tray_log(
                        "開始命令の応答は失敗しましたが、"
                        "Realtime状態遷移を確認しました。"
                        f" session_id={session_id}"
                    )
                    return True

                return False

            if not self._wait_for_realtime_start(
                session_id,
            ):
                tray_log(
                    "Realtime開始通知の待機が"
                    "タイムアウトしました。"
                    f" session_id={session_id}"
                )
                return False

            tray_log(
                "Wake WordからRealtime自動開始を"
                "受け付けました。"
                f" session_id={session_id}"
            )
            return True

        except Exception as error:
            tray_log(
                "Wake Wordからの自動起動処理に失敗しました。"
            )
            tray_log(
                f"{type(error).__name__}: {error}"
            )

            if (
                self.wakeword_manager.active_session_id
                == session_id
                and self.wakeword_manager.state
                in {
                    WakeWordState.CONNECTING,
                    WakeWordState.CONVERSING,
                }
            ):
                return True

            return False

    def _wait_for_realtime_start(
        self,
        session_id: str,
    ) -> bool:
        deadline = (
            time.monotonic()
            + WAKEWORD_REALTIME_START_CONFIRM_TIMEOUT_SECONDS
        )

        while time.monotonic() < deadline:
            active_session_id = (
                self.wakeword_manager.active_session_id
            )
            state = self.wakeword_manager.state

            if active_session_id != session_id:
                return True

            if state is not WakeWordState.ACTIVATING:
                return True

            if self.is_shutting_down:
                return False

            time.sleep(0.05)

        return False

    def recover_realtime_lifecycle_once(self) -> None:
        """
        Bridge停止と管理中Windowの異常終了を1回確認する。

        Windowプロセス終了後はOSがブラウザーの音声リソースを
        解放しているため、残っているセッションを安全に終了できる。
        """

        if self.is_shutting_down:
            return

        if not self.realtime_bridge.is_running:
            tray_log(
                "Realtime通知Bridgeの停止を検知しました。"
                "再起動します。"
            )

            try:
                if self.realtime_bridge.start():
                    tray_log(
                        "Realtime通知Bridgeを再起動しました。"
                    )

            except Exception as error:
                tray_log(
                    "Realtime通知Bridgeの再起動に"
                    "失敗しました。"
                )
                tray_log(
                    f"{type(error).__name__}: {error}"
                )

        exit_code = reap_exited_window_process()

        if exit_code is not None:
            tray_log(
                "Jarvis Windowプロセスの終了を"
                "検知しました。"
                f" exit_code={exit_code}"
            )

            if (
                self.wakeword_manager.state
                in {
                    WakeWordState.ACTIVATING,
                    WakeWordState.CONNECTING,
                    WakeWordState.CONVERSING,
                }
                and self.wakeword_manager.active_session_id
            ):
                self._window_exit_recovery_session_id = (
                    self.wakeword_manager.active_session_id
                )

        recovery_session_id = (
            self._window_exit_recovery_session_id
        )

        if recovery_session_id is None:
            return

        if (
            self.wakeword_manager.active_session_id
            != recovery_session_id
            or self.wakeword_manager.state
            not in {
                WakeWordState.ACTIVATING,
                WakeWordState.CONNECTING,
                WakeWordState.CONVERSING,
            }
        ):
            self._window_exit_recovery_session_id = None
            return

        try:
            accepted = (
                self.wakeword_manager.conversation_finished(
                    reason="window_process_exited",
                    session_id=recovery_session_id,
                )
            )

        except Exception as error:
            tray_log(
                "Window異常終了後のWake Word再開に"
                "失敗しました。再試行します。"
            )
            tray_log(
                f"{type(error).__name__}: {error}"
            )
            return

        if accepted:
            tray_log(
                "Window異常終了後にWake Word待機へ"
                "戻りました。"
                f" session_id={recovery_session_id}"
            )
            self._window_exit_recovery_session_id = None

    def monitor_realtime_lifecycle(self) -> None:
        tray_log(
            "Realtimeライフサイクルの監視を開始します。"
        )

        while not self.is_shutting_down:
            time.sleep(
                REALTIME_LIFECYCLE_MONITOR_INTERVAL_SECONDS
            )
            self.recover_realtime_lifecycle_once()

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
    
    def resume_wakeword_menu_clicked(self,icon,menu_item,):
        tray_log("Wake Word待機を手動で再開します。")
        self.wakeword_manager.resume()
    
    def on_conversation_finished(self):
        """
        Realtime会話終了後にWake Word待機へ戻す。
        """

        tray_log(
            "Realtime会話が終了しました。"
            "Wake Word待機へ戻ります。"
        )

        self.wakeword_manager.conversation_finished()

    def on_realtime_starting(
        self,
        source: str,
        session_id: str,
    ) -> bool:
        """
        WindowがRealtime用マイクを取得する前に、
        Wake Word側のマイクを解放する。
        """

        if self.is_shutting_down:
            return False

        try:
            accepted = (
                self.wakeword_manager.prepare_for_conversation(
                    source=source,
                    session_id=session_id,
                )
            )

        except Exception as error:
            tray_log(
                "Realtime開始準備中にエラーが発生しました。"
            )
            tray_log(
                f"{type(error).__name__}: {error}"
            )
            return False

        if accepted:
            tray_log(
                "Realtime接続開始通知を受け付けました。"
                f" source={source}, session_id={session_id}"
            )
        else:
            tray_log(
                "現在の状態ではRealtime接続を開始できません。"
                f" source={source}, session_id={session_id}"
            )

        return accepted

    def on_realtime_started(
        self,
        source: str,
        session_id: str,
    ) -> bool:
        """
        WindowからRealtimeセッション準備完了を受け取る。
        """

        if self.is_shutting_down:
            return False

        accepted = self.wakeword_manager.conversation_started(
            source=source,
            session_id=session_id,
        )

        if accepted:
            tray_log(
                "Realtime会話開始通知を受け付けました。"
                f" source={source}, session_id={session_id}"
            )
        else:
            tray_log(
                "Realtime会話開始通知を無視しました。"
                f" source={source}, session_id={session_id}"
            )

        return accepted

    def on_realtime_finished(
        self,
        reason: str,
        session_id: str,
    ) -> bool:
        """
        Window側の音声リソース解放後に、
        Wake Word待機を再開する。
        """

        if self.is_shutting_down:
            return False

        accepted = self.wakeword_manager.conversation_finished(
            reason=reason,
            session_id=session_id,
        )

        if accepted:
            tray_log(
                "Realtime終了通知を受け付けました。"
                f" reason={reason}, session_id={session_id}"
            )
        else:
            tray_log(
                "Realtime終了通知を無視しました。"
                f" reason={reason}, session_id={session_id}"
            )

        return accepted

    def restart_menu_clicked(self, icon, menu_item):
        self.restart_jarvis_server()

    def stop_server_menu_clicked(self, icon, menu_item):
        close_jarvis_window()
        stop_jarvis_server()

    def quit_menu_clicked(self, icon, menu_item):
        tray_log("Jarvis Trayを終了します。")

        self.is_shutting_down = True

        try:
            self.realtime_bridge.stop()

        except Exception as error:
            tray_log(
                "Realtime通知Bridge停止時に"
                "エラーが発生しました。"
            )
            tray_log(
                f"{type(error).__name__}: {error}"
            )

        try:
            self.wakeword_manager.stop()

        except Exception as error:
            tray_log(
                "Wake Word停止時にエラーが発生しました。"
            )
            tray_log(
                f"{type(error).__name__}: {error}"
            )

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

        try:
            self.realtime_bridge.start()
            tray_log(
                "Realtime通知Bridgeを起動しました。"
            )

        except Exception as error:
            tray_log(
                "Realtime通知Bridgeの起動に失敗しました。"
            )
            tray_log(
                f"{type(error).__name__}: {error}"
            )

        def start_server_job():
            success = start_jarvis_server()

            if success:
                tray_log(
                    "Jarvisサーバーの起動に成功しました。"
                )

                try:
                    self.wakeword_manager.start()

                except Exception as error:
                    tray_log(
                        "Wake Word待機の開始に失敗しました。"
                    )
                    tray_log(
                        f"{type(error).__name__}: {error}"
                    )

            else:
                tray_log(
                    "Jarvisサーバーは起動できませんでした。"
                    "Trayは起動したままにします。"
                )

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

        realtime_monitor_thread = threading.Thread(
            target=self.monitor_realtime_lifecycle,
            name="RealtimeLifecycleMonitor",
            daemon=True,
        )
        realtime_monitor_thread.start()

    def run(self):
        tray_log("Jarvis Tray mainを開始します。")

        menu = pystray.Menu(
            item("Jarvisを表示", self.open_menu_clicked),
            item("Jarvisを隠す", self.hide_window_menu_clicked),
            item("Jarvisウィンドウを終了", self.close_window_menu_clicked),
            item("状態確認", self.show_status),
            pystray.Menu.SEPARATOR,
            item("Wake Word待機を再開",self.resume_wakeword_menu_clicked),
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
