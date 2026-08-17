import unittest
from unittest.mock import patch

from wakeword.wakeword_manager import (
    WakeWordManager,
    WakeWordState,
)


class FakeWakeWordListener:
    def __init__(self, on_detected):
        self.on_detected = on_detected
        self.start_calls = 0
        self.stop_calls = 0
        self.pause_calls = 0
        self.resume_calls = 0
        self.start_error = None
        self.pause_error = None
        self.resume_error = None

    def start(self):
        self.start_calls += 1

        if self.start_error is not None:
            raise self.start_error

    def stop(self):
        self.stop_calls += 1

    def pause(self):
        self.pause_calls += 1

        if self.pause_error is not None:
            raise self.pause_error

    def resume(self):
        self.resume_calls += 1

        if self.resume_error is not None:
            raise self.resume_error


class ImmediateThread:
    def __init__(
        self,
        target,
        args=(),
        kwargs=None,
        **_options,
    ):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(
            *self._args,
            **self._kwargs,
        )


class WakeWordManagerTests(unittest.TestCase):
    def setUp(self):
        self.activations = []
        self.activation_result = True
        self.activation_error = None
        self.listener = None

        def activate(session_id):
            self.activations.append(session_id)

            if self.activation_error is not None:
                raise self.activation_error

            return self.activation_result

        def listener_factory(on_detected):
            self.listener = FakeWakeWordListener(
                on_detected,
            )
            return self.listener

        self.manager = WakeWordManager(
            on_activate_jarvis=activate,
            listener_factory=listener_factory,
        )

        self.thread_patcher = patch(
            "wakeword.wakeword_manager.threading.Thread",
            ImmediateThread,
        )
        self.thread_patcher.start()
        self.addCleanup(self.thread_patcher.stop)

    def test_start_and_stop_are_idempotent(self):
        self.assertEqual(
            self.manager.state,
            WakeWordState.STOPPED,
        )

        self.assertTrue(self.manager.start())
        self.assertFalse(self.manager.start())

        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )
        self.assertEqual(self.listener.start_calls, 1)

        self.assertTrue(self.manager.stop())
        self.assertFalse(self.manager.stop())

        self.assertEqual(
            self.manager.state,
            WakeWordState.STOPPED,
        )
        self.assertEqual(self.listener.stop_calls, 1)

    def test_start_failure_restores_stopped_state(self):
        self.listener.start_error = RuntimeError(
            "start failed"
        )

        with self.assertRaises(RuntimeError):
            self.manager.start()

        self.assertEqual(
            self.manager.state,
            WakeWordState.STOPPED,
        )
        self.assertIsNone(
            self.manager.active_session_id
        )

    def test_wakeword_detection_creates_one_session(self):
        self.manager.start()

        self.listener.on_detected(0.9)

        self.assertEqual(
            self.manager.state,
            WakeWordState.ACTIVATING,
        )
        self.assertEqual(len(self.activations), 1)
        self.assertEqual(
            self.manager.active_session_id,
            self.activations[0],
        )
        self.assertEqual(
            self.manager.active_source,
            "wakeword",
        )

        self.listener.on_detected(0.95)

        self.assertEqual(len(self.activations), 1)

    def test_false_activation_result_resumes_waiting(self):
        self.activation_result = False
        self.manager.start()

        self.listener.on_detected(0.9)

        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )
        self.assertIsNone(
            self.manager.active_session_id
        )
        self.assertEqual(self.listener.resume_calls, 1)

    def test_wakeword_session_moves_through_realtime_states(self):
        self.manager.start()
        self.listener.on_detected(0.9)

        session_id = self.manager.active_session_id

        self.assertTrue(
            self.manager.prepare_for_conversation(
                source="wakeword",
                session_id=session_id,
            )
        )
        self.assertEqual(
            self.manager.state,
            WakeWordState.CONNECTING,
        )
        self.assertEqual(
            self.manager.active_source,
            "wakeword",
        )

        self.assertTrue(
            self.manager.conversation_started(
                source="wakeword",
                session_id=session_id,
            )
        )
        self.assertEqual(
            self.manager.state,
            WakeWordState.CONVERSING,
        )

        self.assertTrue(
            self.manager.conversation_finished(
                reason="connection_closed",
                session_id=session_id,
            )
        )
        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )
        self.assertEqual(self.listener.pause_calls, 1)
        self.assertEqual(self.listener.resume_calls, 1)

    def test_activation_exception_resumes_waiting(self):
        self.activation_error = RuntimeError(
            "window failed"
        )
        self.manager.start()

        self.listener.on_detected(0.9)

        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )
        self.assertEqual(self.listener.resume_calls, 1)

    def test_manual_conversation_flow_is_session_safe(self):
        self.manager.start()

        self.assertTrue(
            self.manager.prepare_for_conversation(
                source="manual",
                session_id="session-1",
            )
        )
        self.assertEqual(
            self.manager.state,
            WakeWordState.CONNECTING,
        )
        self.assertEqual(self.listener.pause_calls, 1)

        self.assertTrue(
            self.manager.prepare_for_conversation(
                source="manual",
                session_id="session-1",
            )
        )
        self.assertEqual(self.listener.pause_calls, 1)

        self.assertFalse(
            self.manager.prepare_for_conversation(
                source="manual",
                session_id="session-2",
            )
        )
        self.assertFalse(
            self.manager.conversation_started(
                source="manual",
                session_id="session-2",
            )
        )

        self.assertTrue(
            self.manager.conversation_started(
                source="manual",
                session_id="session-1",
            )
        )
        self.assertTrue(
            self.manager.conversation_started(
                source="manual",
                session_id="session-1",
            )
        )
        self.assertEqual(
            self.manager.state,
            WakeWordState.CONVERSING,
        )

        self.assertFalse(self.manager.resume())
        self.assertEqual(self.listener.resume_calls, 0)

        self.assertFalse(
            self.manager.conversation_finished(
                reason="stale",
                session_id="session-2",
            )
        )
        self.assertTrue(
            self.manager.conversation_finished(
                reason="manual_disconnect",
                session_id="session-1",
            )
        )
        self.assertFalse(
            self.manager.conversation_finished(
                reason="duplicate",
                session_id="session-1",
            )
        )

        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )
        self.assertEqual(self.listener.resume_calls, 1)

    def test_stale_failure_does_not_cancel_new_session(self):
        self.manager.start()
        self.listener.on_detected(0.9)

        first_session_id = (
            self.manager.active_session_id
        )

        self.assertTrue(self.manager.resume())

        self.listener.on_detected(0.95)
        second_session_id = (
            self.manager.active_session_id
        )

        self.assertNotEqual(
            first_session_id,
            second_session_id,
        )
        self.assertFalse(
            self.manager.activation_failed(
                session_id=first_session_id,
            )
        )
        self.assertEqual(
            self.manager.state,
            WakeWordState.ACTIVATING,
        )
        self.assertEqual(
            self.manager.active_session_id,
            second_session_id,
        )

    def test_pause_failure_returns_to_waiting(self):
        self.manager.start()
        self.listener.pause_error = RuntimeError(
            "microphone release failed"
        )

        with self.assertRaises(RuntimeError):
            self.manager.prepare_for_conversation(
                source="manual",
                session_id="session-1",
            )

        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )
        self.assertEqual(self.listener.resume_calls, 1)

    def test_resume_failure_keeps_session_for_retry(self):
        self.manager.start()
        self.assertTrue(
            self.manager.prepare_for_conversation(
                source="manual",
                session_id="session-1",
            )
        )
        self.assertTrue(
            self.manager.conversation_started(
                source="manual",
                session_id="session-1",
            )
        )

        self.listener.resume_error = RuntimeError(
            "device is still busy"
        )

        with self.assertRaises(RuntimeError):
            self.manager.conversation_finished(
                reason="manual_disconnect",
                session_id="session-1",
            )

        self.assertEqual(
            self.manager.state,
            WakeWordState.CONVERSING,
        )
        self.assertEqual(
            self.manager.active_session_id,
            "session-1",
        )

        self.listener.resume_error = None

        self.assertTrue(
            self.manager.conversation_finished(
                reason="manual_disconnect_retry",
                session_id="session-1",
            )
        )
        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )
        self.assertIsNone(
            self.manager.active_session_id
        )
        self.assertEqual(self.listener.resume_calls, 2)

    def test_stale_wakeword_start_is_rejected(self):
        self.manager.start()

        self.assertFalse(
            self.manager.prepare_for_conversation(
                source="wakeword",
                session_id="expired-session",
            )
        )
        self.assertEqual(
            self.manager.state,
            WakeWordState.WAITING,
        )
        self.assertIsNone(
            self.manager.active_session_id
        )
        self.assertEqual(self.listener.pause_calls, 0)


if __name__ == "__main__":
    unittest.main()
