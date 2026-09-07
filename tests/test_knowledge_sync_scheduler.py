import unittest

from types import SimpleNamespace
from unittest.mock import Mock

from tray.knowledge_sync_scheduler import KnowledgeSyncScheduler


class KnowledgeSyncSchedulerTests(unittest.TestCase):
    def test_disabled_scheduler_does_not_start(self):
        scheduler = KnowledgeSyncScheduler(enabled=False)

        self.assertFalse(scheduler.start())

    def test_run_once_uses_apply_and_returns_process_status(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0))
        scheduler = KnowledgeSyncScheduler(
            enabled=True,
            interval_minutes=15,
            runner=runner,
        )

        result = scheduler.run_once()

        self.assertEqual(result, 0)
        command = runner.call_args.args[0]
        self.assertEqual(command[-1], "--apply")
        self.assertTrue(command[-2].endswith("sync_notion_knowledge.py"))
        self.assertFalse(runner.call_args.kwargs["shell"] if "shell" in runner.call_args.kwargs else False)

    def test_runner_failure_is_contained(self):
        scheduler = KnowledgeSyncScheduler(
            enabled=True,
            runner=Mock(side_effect=OSError("failed")),
        )

        self.assertEqual(scheduler.run_once(), 1)


if __name__ == "__main__":
    unittest.main()

