import json
import unittest
import urllib.error
import urllib.request

from core.config import SERVER_URL
from tray.realtime_bridge import TrayRealtimeBridge
from wakeword.wakeword_manager import (
    WakeWordManager,
    WakeWordState,
)


class FakeWakeWordListener:
    def __init__(self, on_detected):
        self.on_detected = on_detected
        self.pause_calls = 0
        self.resume_calls = 0

    def start(self):
        return None

    def stop(self):
        return None

    def pause(self):
        self.pause_calls += 1

    def resume(self):
        self.resume_calls += 1


class TrayRealtimeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.listener = None

        def listener_factory(on_detected):
            self.listener = FakeWakeWordListener(
                on_detected,
            )
            return self.listener

        self.manager = WakeWordManager(
            on_activate_jarvis=lambda _session_id: True,
            listener_factory=listener_factory,
        )
        self.manager.start()

        self.bridge = TrayRealtimeBridge(
            on_starting=(
                lambda source, session_id:
                self.manager.prepare_for_conversation(
                    source=source,
                    session_id=session_id,
                )
            ),
            on_started=(
                lambda source, session_id:
                self.manager.conversation_started(
                    source=source,
                    session_id=session_id,
                )
            ),
            on_finished=(
                lambda reason, session_id:
                self.manager.conversation_finished(
                    reason=reason,
                    session_id=session_id,
                )
            ),
            port=0,
        )
        self.bridge.start()
        self.base_url = (
            f"http://127.0.0.1:{self.bridge.port}"
        )

    def tearDown(self):
        self.bridge.stop()
        self.manager.stop()

    def request(
        self,
        path,
        *,
        method="GET",
        payload=None,
        origin=None,
        content_type="application/json",
    ):
        headers = {}
        data = None

        if origin is not None:
            headers["Origin"] = origin

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = content_type

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )

        try:
            response = urllib.request.urlopen(
                request,
                timeout=2,
            )

        except urllib.error.HTTPError as error:
            response = error

        raw_body = response.read()
        body = (
            json.loads(raw_body.decode("utf-8"))
            if raw_body
            else None
        )

        return response.status, response.headers, body

    def test_health_and_start_stop_are_idempotent(self):
        self.assertTrue(self.bridge.is_running)

        status, _headers, body = self.request(
            "/health",
        )

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertFalse(self.bridge.start())
        self.assertTrue(self.bridge.stop())
        self.assertFalse(self.bridge.is_running)
        self.assertFalse(self.bridge.stop())
        self.assertTrue(self.bridge.start())
        self.assertTrue(self.bridge.is_running)

    def test_manual_lifecycle_reaches_waiting_again(self):
        status, _headers, body = self.request(
            "/realtime/starting",
            method="POST",
            payload={
                "source": "manual",
                "session_id": "session-1",
            },
            origin=SERVER_URL,
        )

        self.assertEqual(status, 200)
        self.assertTrue(body["accepted"])
        self.assertEqual(
            self.manager.state,
            WakeWordState.CONNECTING,
        )
        self.assertEqual(self.listener.pause_calls, 1)

        duplicate_status, _headers, _body = self.request(
            "/realtime/starting",
            method="POST",
            payload={
                "source": "manual",
                "session_id": "session-1",
            },
            origin=SERVER_URL,
        )

        self.assertEqual(duplicate_status, 200)
        self.assertEqual(self.listener.pause_calls, 1)

        started_status, _headers, _body = self.request(
            "/realtime/started",
            method="POST",
            payload={
                "source": "manual",
                "session_id": "session-1",
            },
            origin=SERVER_URL,
        )

        self.assertEqual(started_status, 200)
        self.assertEqual(
            self.manager.state,
            WakeWordState.CONVERSING,
        )

        finished_status, _headers, _body = self.request(
            "/realtime/finished",
            method="POST",
            payload={
                "reason": "manual_disconnect",
                "session_id": "session-1",
            },
            origin=SERVER_URL,
        )

        self.assertEqual(finished_status, 200)
        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )
        self.assertEqual(self.listener.resume_calls, 1)

        duplicate_status, _headers, _body = self.request(
            "/realtime/finished",
            method="POST",
            payload={
                "reason": "duplicate",
                "session_id": "session-1",
            },
            origin=SERVER_URL,
        )

        self.assertEqual(duplicate_status, 409)
        self.assertEqual(self.listener.resume_calls, 1)

    def test_idle_timeout_finished_resumes_wakeword_waiting(self):
        for path in ("starting", "started"):
            status, _headers, body = self.request(
                f"/realtime/{path}",
                method="POST",
                payload={
                    "source": "manual",
                    "session_id": "idle-session",
                },
                origin=SERVER_URL,
            )
            self.assertEqual(status, 200)
            self.assertTrue(body["accepted"])

        status, _headers, body = self.request(
            "/realtime/finished",
            method="POST",
            payload={
                "reason": "idle_timeout",
                "session_id": "idle-session",
            },
            origin=SERVER_URL,
        )

        self.assertEqual(status, 200)
        self.assertTrue(body["accepted"])
        self.assertEqual(self.manager.state, WakeWordState.WAITING)
        self.assertEqual(self.listener.resume_calls, 1)

    def test_stale_session_notifications_are_rejected(self):
        self.request(
            "/realtime/starting",
            method="POST",
            payload={
                "source": "manual",
                "session_id": "current-session",
            },
        )

        started_status, _headers, _body = self.request(
            "/realtime/started",
            method="POST",
            payload={
                "source": "manual",
                "session_id": "stale-session",
            },
        )
        finished_status, _headers, _body = self.request(
            "/realtime/finished",
            method="POST",
            payload={
                "reason": "stale",
                "session_id": "stale-session",
            },
        )

        self.assertEqual(started_status, 409)
        self.assertEqual(finished_status, 409)
        self.assertEqual(
            self.manager.state,
            WakeWordState.CONNECTING,
        )
        self.assertEqual(self.listener.resume_calls, 0)

    def test_startup_failure_returns_to_waiting(self):
        starting_status, _headers, _body = self.request(
            "/realtime/starting",
            method="POST",
            payload={
                "source": "manual",
                "session_id": "failed-session",
            },
        )
        finished_status, _headers, _body = self.request(
            "/realtime/finished",
            method="POST",
            payload={
                "reason": "startup_failed",
                "session_id": "failed-session",
            },
        )

        self.assertEqual(starting_status, 200)
        self.assertEqual(finished_status, 200)
        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )
        self.assertEqual(self.listener.pause_calls, 1)
        self.assertEqual(self.listener.resume_calls, 1)

    def test_validation_and_cors(self):
        options_status, options_headers, _body = (
            self.request(
                "/realtime/starting",
                method="OPTIONS",
                origin=SERVER_URL,
            )
        )

        self.assertEqual(options_status, 204)
        self.assertEqual(
            options_headers["Access-Control-Allow-Origin"],
            SERVER_URL,
        )

        forbidden_status, _headers, _body = self.request(
            "/realtime/starting",
            method="POST",
            payload={
                "source": "manual",
                "session_id": "session-1",
            },
            origin="https://example.com",
        )
        missing_id_status, _headers, _body = self.request(
            "/realtime/starting",
            method="POST",
            payload={"source": "manual"},
            origin=SERVER_URL,
        )

        self.assertEqual(forbidden_status, 403)
        self.assertEqual(missing_id_status, 400)
        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )


if __name__ == "__main__":
    unittest.main()
