import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


try:
    import pystray  # noqa: F401
except ModuleNotFoundError:
    pystray_stub = types.ModuleType("pystray")
    pystray_stub.MenuItem = object
    pystray_stub.Menu = object
    pystray_stub.Icon = object
    sys.modules["pystray"] = pystray_stub


from tray.tray_app import TrayApp
from wakeword.wakeword_manager import WakeWordState


class TrayWakeWordActivationTests(unittest.TestCase):
    def make_app(self):
        app = TrayApp.__new__(TrayApp)
        app.is_shutting_down = False
        app._window_exit_recovery_session_id = None
        app.realtime_bridge = SimpleNamespace(
            is_running=True,
            start=Mock(return_value=False),
        )
        app.wakeword_manager = SimpleNamespace(
            active_session_id="session-1",
            state=WakeWordState.ACTIVATING,
        )
        app.show_jarvis_window = Mock(return_value=True)
        app._wait_for_realtime_start = Mock(
            return_value=True,
        )
        return app

    def test_wakeword_shows_window_and_starts_same_session(self):
        app = self.make_app()

        with (
            patch(
                "tray.tray_app.start_realtime_voice",
                return_value=True,
            ) as start_mock,
            patch("tray.tray_app.tray_log"),
        ):
            accepted = app.on_wakeword_detected(
                "session-1"
            )

        self.assertTrue(accepted)
        app.show_jarvis_window.assert_called_once_with()
        start_mock.assert_called_once_with(
            source="wakeword",
            session_id="session-1",
        )
        app._wait_for_realtime_start.assert_called_once_with(
            "session-1"
        )

    def test_wakeword_recovers_when_command_is_rejected(self):
        app = self.make_app()
        app._wait_for_realtime_start.return_value = False

        with (
            patch(
                "tray.tray_app.start_realtime_voice",
                return_value=False,
            ),
            patch("tray.tray_app.tray_log"),
        ):
            accepted = app.on_wakeword_detected(
                "session-1"
            )

        self.assertFalse(accepted)
        app._wait_for_realtime_start.assert_called_once_with(
            "session-1"
        )

    def test_lost_command_response_keeps_progressed_session(self):
        app = self.make_app()

        with (
            patch(
                "tray.tray_app.start_realtime_voice",
                return_value=False,
            ),
            patch("tray.tray_app.tray_log"),
        ):
            accepted = app.on_wakeword_detected(
                "session-1"
            )

        self.assertTrue(accepted)
        app._wait_for_realtime_start.assert_called_once_with(
            "session-1"
        )

    def test_start_confirmation_detects_transition_or_timeout(self):
        app = self.make_app()

        app.wakeword_manager.state = (
            WakeWordState.CONNECTING
        )
        self.assertTrue(
            TrayApp._wait_for_realtime_start(
                app,
                "session-1",
            )
        )

        app.wakeword_manager.state = (
            WakeWordState.ACTIVATING
        )

        with patch(
            "tray.tray_app."
            "WAKEWORD_REALTIME_START_CONFIRM_TIMEOUT_SECONDS",
            0,
        ):
            self.assertFalse(
                TrayApp._wait_for_realtime_start(
                    app,
                    "session-1",
                )
            )

    def test_restarts_stopped_realtime_bridge(self):
        app = self.make_app()
        app.realtime_bridge.is_running = False
        app.realtime_bridge.start.return_value = True

        with (
            patch(
                "tray.tray_app.reap_exited_window_process",
                return_value=None,
            ),
            patch("tray.tray_app.tray_log"),
        ):
            app.recover_realtime_lifecycle_once()

        app.realtime_bridge.start.assert_called_once_with()

    def test_window_process_exit_finishes_active_session(self):
        app = self.make_app()
        app.wakeword_manager = SimpleNamespace(
            active_session_id="session-1",
            state=WakeWordState.CONVERSING,
            conversation_finished=Mock(return_value=True),
        )

        with (
            patch(
                "tray.tray_app.reap_exited_window_process",
                return_value=9,
            ),
            patch("tray.tray_app.tray_log"),
        ):
            app.recover_realtime_lifecycle_once()

        app.wakeword_manager.conversation_finished.assert_called_once_with(
            reason="window_process_exited",
            session_id="session-1",
        )
        self.assertIsNone(
            app._window_exit_recovery_session_id
        )

    def test_window_exit_recovery_retries_resume_failure(self):
        app = self.make_app()
        app.wakeword_manager = SimpleNamespace(
            active_session_id="session-1",
            state=WakeWordState.CONNECTING,
            conversation_finished=Mock(
                side_effect=[
                    RuntimeError("device busy"),
                    True,
                ]
            ),
        )

        with (
            patch(
                "tray.tray_app.reap_exited_window_process",
                side_effect=[7, None],
            ),
            patch("tray.tray_app.tray_log"),
        ):
            app.recover_realtime_lifecycle_once()
            app.recover_realtime_lifecycle_once()

        self.assertEqual(
            app.wakeword_manager.conversation_finished.call_count,
            2,
        )
        self.assertIsNone(
            app._window_exit_recovery_session_id
        )


if __name__ == "__main__":
    unittest.main()
