import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

from core.config import (
    SERVER_URL,
    TRAY_REALTIME_BRIDGE_URL,
    WEB_UI_VERSION,
    WINDOW_CONTROL_URL,
    WINDOW_APP_URL,
    WINDOW_REALTIME_COMMAND_TIMEOUT_SECONDS,
)
from tray import window_client
from window.control_server import WindowControlServer
from window import tray_client
from window.window_controller import WindowController


BASE_DIR = Path(__file__).resolve().parent.parent


class FakeLoadedEvent:
    def __init__(self, ready):
        self.ready = ready
        self.wait_calls = []

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        return self.ready


class FakeWindow:
    def __init__(self, *, ready=True, result=None, error=None):
        self.events = type(
            "FakeEvents",
            (),
            {"loaded": FakeLoadedEvent(ready)},
        )()
        self.result = result
        self.error = error
        self.scripts = []

    def evaluate_js(self, script):
        self.scripts.append(script)

        if self.error is not None:
            raise self.error

        return self.result


class WindowControllerRealtimeTests(unittest.TestCase):
    def setUp(self):
        self.log_patcher = patch(
            "window.window_controller.window_log"
        )
        self.log_patcher.start()
        self.addCleanup(self.log_patcher.stop)
        self.state_patcher = patch(
            "window.window_controller.save_current_window_state"
        )
        self.state_patcher.start()
        self.addCleanup(self.state_patcher.stop)

    def test_waits_for_page_and_dispatches_safe_script(self):
        controller = WindowController()
        window = FakeWindow(ready=True, result=None)
        controller.set_window(window)

        source = 'wake"word'
        session_id = "session\\id"

        self.assertTrue(
            controller.start_realtime(
                source=source,
                session_id=session_id,
                ready_timeout=1.5,
            )
        )
        self.assertEqual(
            window.events.loaded.wait_calls,
            [1.5],
        )
        self.assertEqual(len(window.scripts), 1)
        self.assertIn(
            json.dumps(source, ensure_ascii=False),
            window.scripts[0],
        )
        self.assertIn(
            json.dumps(session_id, ensure_ascii=False),
            window.scripts[0],
        )
        self.assertIn(
            "Jarvis Realtime API is not ready.",
            window.scripts[0],
        )
        self.assertIn(
            "Jarvis Realtime start was rejected.",
            window.scripts[0],
        )

    def test_rejects_unready_or_javascript_failure(self):
        controller = WindowController()
        unready_window = FakeWindow(
            ready=False,
        )
        controller.set_window(unready_window)

        self.assertFalse(
            controller.start_realtime(
                source="wakeword",
                session_id="session-1",
                ready_timeout=0,
            )
        )
        self.assertEqual(unready_window.scripts, [])

        failed_window = FakeWindow(
            ready=True,
            error=RuntimeError("start rejected"),
        )
        controller.set_window(failed_window)

        self.assertFalse(
            controller.start_realtime(
                source="wakeword",
                session_id="session-2",
                ready_timeout=0,
            )
        )

    def test_rejects_invalid_or_unavailable_window(self):
        controller = WindowController()

        self.assertFalse(
            controller.start_realtime(
                source="wakeword",
                session_id="session-1",
                ready_timeout=0,
            )
        )

        controller.set_window(FakeWindow())

        self.assertFalse(
            controller.start_realtime(
                source="",
                session_id="session-1",
                ready_timeout=0,
            )
        )

    def test_window_close_notifies_active_session_once(self):
        notify_closed = Mock(return_value=True)
        controller = WindowController(
            on_realtime_window_closed=notify_closed,
        )
        controller.set_window(FakeWindow())

        self.assertTrue(
            controller.start_realtime(
                source="wakeword",
                session_id="session-1",
                ready_timeout=0,
            )
        )

        controller.on_closed()
        controller.on_closed()

        notify_closed.assert_called_once_with(
            "window_closed",
            "session-1",
        )


class FakeControlController:
    def __init__(self):
        self.accepted = True
        self.calls = []

    def start_realtime(self, source, session_id):
        self.calls.append((source, session_id))
        return self.accepted


class WindowControlServerRealtimeTests(unittest.TestCase):
    def setUp(self):
        self.log_patcher = patch(
            "window.control_server.window_log"
        )
        self.log_patcher.start()

        self.controller = FakeControlController()
        self.server = WindowControlServer(
            self.controller,
            host="127.0.0.1",
            port=0,
        )
        self.server_thread = threading.Thread(
            target=self.server.start,
            daemon=True,
        )
        self.server_thread.start()

        deadline = time.monotonic() + 2

        while (
            self.server.server is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)

        if self.server.server is None:
            self.fail("Window control server did not start")

        self.base_url = (
            f"http://127.0.0.1:{self.server.port}"
        )

    def tearDown(self):
        self.server.stop()
        self.server_thread.join(timeout=2)
        self.log_patcher.stop()

    def post(self, path, payload):
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            response = urllib.request.urlopen(
                request,
                timeout=2,
            )

        except urllib.error.HTTPError as error:
            response = error

        body = json.loads(
            response.read().decode("utf-8")
        )
        return response.status, body

    def test_realtime_start_endpoint(self):
        status, body = self.post(
            "/realtime/start",
            {
                "source": "wakeword",
                "session_id": "session-1",
            },
        )

        self.assertEqual(status, 200)
        self.assertTrue(body["accepted"])
        self.assertEqual(
            self.controller.calls,
            [("wakeword", "session-1")],
        )

        self.controller.accepted = False
        rejected_status, rejected_body = self.post(
            "/realtime/start",
            {
                "source": "wakeword",
                "session_id": "session-2",
            },
        )

        self.assertEqual(rejected_status, 409)
        self.assertFalse(rejected_body["accepted"])

    def test_realtime_start_endpoint_validates_body(self):
        status, body = self.post(
            "/realtime/start",
            {"source": "wakeword"},
        )

        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])

        unsupported_status, unsupported_body = self.post(
            "/realtime/start",
            {
                "source": "manual",
                "session_id": "session-1",
            },
        )

        self.assertEqual(unsupported_status, 400)
        self.assertFalse(unsupported_body["ok"])
        self.assertEqual(self.controller.calls, [])


class FakeUrlopenResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(
            {"accepted": True}
        ).encode("utf-8")


class WindowTrayClientTests(unittest.TestCase):
    def test_notifies_tray_after_window_cleanup(self):
        with (
            patch(
                "window.tray_client.urllib.request.urlopen",
                return_value=FakeUrlopenResponse(),
            ) as urlopen_mock,
            patch("window.tray_client.window_log"),
        ):
            accepted = tray_client.notify_realtime_finished(
                reason="window_closed",
                session_id="session-1",
            )

        self.assertTrue(accepted)

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(
            request.full_url,
            (
                f"{TRAY_REALTIME_BRIDGE_URL}"
                "/realtime/finished"
            ),
        )
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {
                "reason": "window_closed",
                "session_id": "session-1",
            },
        )

    def test_retries_transient_window_close_notification(self):
        with (
            patch(
                "window.tray_client.urllib.request.urlopen",
                side_effect=[
                    urllib.error.URLError("temporary"),
                    FakeUrlopenResponse(),
                ],
            ) as urlopen_mock,
            patch("window.tray_client.time.sleep") as sleep_mock,
            patch("window.tray_client.window_log"),
        ):
            accepted = tray_client.notify_realtime_finished(
                reason="window_closed",
                session_id="session-1",
                retry_count=3,
                retry_delay=0.01,
            )

        self.assertTrue(accepted)
        self.assertEqual(urlopen_mock.call_count, 2)
        sleep_mock.assert_called_once_with(0.01)

    def test_retries_server_error_from_tray_bridge(self):
        server_error = urllib.error.HTTPError(
            (
                f"{TRAY_REALTIME_BRIDGE_URL}"
                "/realtime/finished"
            ),
            503,
            "Service unavailable",
            None,
            None,
        )

        with (
            patch(
                "window.tray_client.urllib.request.urlopen",
                side_effect=[
                    server_error,
                    FakeUrlopenResponse(),
                ],
            ) as urlopen_mock,
            patch("window.tray_client.time.sleep") as sleep_mock,
            patch("window.tray_client.window_log"),
        ):
            accepted = tray_client.notify_realtime_finished(
                reason="window_closed",
                session_id="session-1",
                retry_count=3,
                retry_delay=0.01,
            )

        self.assertTrue(accepted)
        self.assertEqual(urlopen_mock.call_count, 2)
        sleep_mock.assert_called_once_with(0.01)

    def test_duplicate_finished_notification_is_complete(self):
        duplicate_error = urllib.error.HTTPError(
            (
                f"{TRAY_REALTIME_BRIDGE_URL}"
                "/realtime/finished"
            ),
            409,
            "Conflict",
            None,
            None,
        )

        with (
            patch(
                "window.tray_client.urllib.request.urlopen",
                side_effect=duplicate_error,
            ) as urlopen_mock,
            patch("window.tray_client.time.sleep") as sleep_mock,
            patch("window.tray_client.window_log"),
        ):
            accepted = tray_client.notify_realtime_finished(
                reason="window_closed",
                session_id="session-1",
            )

        self.assertTrue(accepted)
        self.assertEqual(urlopen_mock.call_count, 1)
        sleep_mock.assert_not_called()


class WindowClientRealtimeTests(unittest.TestCase):
    def test_reaps_exited_managed_window_process_once(self):
        exited_process = Mock()
        exited_process.poll.return_value = 7

        with patch.object(
            window_client,
            "window_process",
            exited_process,
        ):
            self.assertEqual(
                window_client.reap_exited_window_process(),
                7,
            )
            self.assertIsNone(
                window_client.window_process
            )
            self.assertIsNone(
                window_client.reap_exited_window_process()
            )

    def test_does_not_reap_running_window_process(self):
        running_process = Mock()
        running_process.poll.return_value = None

        with patch.object(
            window_client,
            "window_process",
            running_process,
        ):
            self.assertIsNone(
                window_client.reap_exited_window_process()
            )
            self.assertIs(
                window_client.window_process,
                running_process,
            )

    def test_sends_session_aware_start_command(self):
        with (
            patch(
                "tray.window_client.urllib.request.urlopen",
                return_value=FakeUrlopenResponse(),
            ) as urlopen_mock,
            patch("tray.window_client.tray_log"),
        ):
            accepted = window_client.start_realtime_voice(
                source="wakeword",
                session_id="session-1",
            )

        self.assertTrue(accepted)

        request = urlopen_mock.call_args.args[0]
        self.assertEqual(
            request.full_url,
            f"{WINDOW_CONTROL_URL}/realtime/start",
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {
                "source": "wakeword",
                "session_id": "session-1",
            },
        )
        self.assertEqual(
            urlopen_mock.call_args.kwargs["timeout"],
            WINDOW_REALTIME_COMMAND_TIMEOUT_SECONDS,
        )

    def test_show_window_reports_command_result(self):
        with (
            patch(
                "tray.window_client.ensure_jarvis_window_process",
                return_value=True,
            ),
            patch(
                "tray.window_client.send_window_command",
                return_value=True,
            ),
            patch("tray.window_client.tray_log"),
        ):
            self.assertTrue(
                window_client.show_jarvis_window(
                    is_server_alive_func=lambda: True,
                    start_server_func=lambda: True,
                )
            )


class WindowStaticAssetTests(unittest.TestCase):
    def test_index_uses_versioned_realtime_script(self):
        index_html = (
            BASE_DIR / "static" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn(
            f"/static/script.js?v={WEB_UI_VERSION}",
            index_html,
        )
        self.assertEqual(
            WINDOW_APP_URL,
            f"{SERVER_URL}/?v={WEB_UI_VERSION}",
        )

    def test_script_has_retryable_terminal_notification(self):
        script = (
            BASE_DIR / "static" / "script.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "async function notifyTrayRealtimeFinished",
            script,
        )
        self.assertIn(
            "REALTIME_FINISHED_NOTIFY_RETRY_COUNT = 8",
            script,
        )
        self.assertIn(
            "acceptConflict && response.status === 409",
            script,
        )
        self.assertIn(
            'console.warn("Local audio track stop error:", error)',
            script,
        )

    def test_script_configures_realtime_noise_controls(self):
        script = (
            BASE_DIR / "static" / "script.js"
        ).read_text(encoding="utf-8")

        for constraint in (
            "echoCancellation: true",
            "noiseSuppression: true",
            "autoGainControl: true",
        ):
            self.assertIn(constraint, script)

        self.assertIn(
            "audio: REALTIME_MEDIA_AUDIO_CONSTRAINTS",
            script,
        )
        self.assertIn(
            'REALTIME_INPUT_NOISE_REDUCTION_TYPE = "far_field"',
            script,
        )
        self.assertIn(
            "noise_reduction: {",
            script,
        )
        self.assertIn(
            "type: REALTIME_INPUT_NOISE_REDUCTION_TYPE",
            script,
        )
        self.assertIn(
            "REALTIME_SERVER_VAD_THRESHOLD = 0.8",
            script,
        )
        self.assertIn(
            "threshold: REALTIME_SERVER_VAD_THRESHOLD",
            script,
        )
        self.assertIn(
            "REALTIME_SERVER_VAD_SILENCE_DURATION_MS = 1200",
            script,
        )
        self.assertIn(
            "silence_duration_ms:",
            script,
        )
        self.assertIn(
            "REALTIME_SERVER_VAD_SILENCE_DURATION_MS,",
            script,
        )
        self.assertIn(
            'type: "server_vad"',
            script,
        )
        self.assertIn(
            "create_response: false",
            script,
        )
        self.assertIn(
            "interrupt_response: false",
            script,
        )

        # Existing transcription and tool-calling paths must remain present.
        self.assertIn(
            'type: "realtime"',
            script,
        )
        self.assertIn(
            "transcription: {",
            script,
        )
        self.assertIn(
            'model: "gpt-4o-mini-transcribe"',
            script,
        )
        self.assertIn(
            'language: "ja"',
            script,
        )
        self.assertIn(
            'data.type === "response.function_call_arguments.done"',
            script,
        )

    def test_script_guards_barge_in_while_realtime_audio_is_playing(self):
        script = (
            BASE_DIR / "static" / "script.js"
        ).read_text(encoding="utf-8")

        for expected in (
            "REALTIME_BARGE_IN_GUARD_MS = 600",
            "REALTIME_BARGE_IN_MIN_TRANSCRIPT_CHARACTERS = 2",
            'data.type === "output_audio_buffer.started"',
            'data.type === "output_audio_buffer.stopped"',
            'data.type === "output_audio_buffer.cleared"',
            'data.type === "input_audio_buffer.speech_started"',
            'data.type === "input_audio_buffer.speech_stopped"',
            "if (isRealtimeOutputAudioPlaying)",
            "startRealtimeBargeInGuard(sessionId)",
            "clearRealtimeBargeInTimer()",
            "guardedTurn.guardDurationMet = true",
            "isMeaningfulRealtimeUserTranscript(transcript, isBargeIn)",
            "(isBargeIn && !passedBargeInGuard)",
            "speechTurn.responseRequested = requestRealtimeResponse(sessionId)",
            "requestRealtimeResponse(sessionId)",
            'type: "response.cancel"',
            'type: "output_audio_buffer.clear"',
            "resetRealtimeBargeInState();",
        ):
            self.assertIn(expected, script)

        cancel_position = script.index('type: "response.cancel"')
        clear_position = script.index('type: "output_audio_buffer.clear"')
        self.assertLess(cancel_position, clear_position)

        guard_start = script.index("function startRealtimeBargeInGuard")
        interrupt_start = script.index("function interruptRealtimeResponse")
        guard_source = script[guard_start:interrupt_start]
        self.assertNotIn("interruptRealtimeResponse(sessionId)", guard_source)

    def test_script_preserves_realtime_events_tools_and_cleanup(self):
        script = (
            BASE_DIR / "static" / "script.js"
        ).read_text(encoding="utf-8")

        for expected in (
            'data.type === "session.created"',
            'data.type === "response.function_call_arguments.done"',
            'data.type === "input_audio_buffer.speech_started"',
            'data.type === "input_audio_buffer.speech_stopped"',
            'data.type === "response.done"',
            'fetch("/realtime/tools", {',
            'type: "function_call_output"',
            'type: "response.create"',
            "currentDataChannel.close()",
            "currentPeerConnection.close()",
            "currentLocalStream.getTracks()",
            "track.stop()",
            "currentRemoteAudioElement.srcObject = null",
            "resetRealtimeBargeInState();",
        ):
            self.assertIn(expected, script)


if __name__ == "__main__":
    unittest.main()
