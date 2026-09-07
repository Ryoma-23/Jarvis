import subprocess
import threading

from collections.abc import Callable

from app.config import (
    BASE_DIR,
    NOTION_KNOWLEDGE_SYNC_ENABLED,
    NOTION_KNOWLEDGE_SYNC_INTERVAL_MINUTES,
)
from core.config import VENV_PYTHON
from core.logger import tray_log


KNOWLEDGE_SYNC_SCRIPT = BASE_DIR / "scripts" / "sync_notion_knowledge.py"
KNOWLEDGE_SYNC_TIMEOUT_SECONDS = 60 * 60


class KnowledgeSyncScheduler:
    def __init__(
        self,
        *,
        enabled: bool = NOTION_KNOWLEDGE_SYNC_ENABLED,
        interval_minutes: int = NOTION_KNOWLEDGE_SYNC_INTERVAL_MINUTES,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self._enabled = enabled
        self._interval_seconds = interval_minutes * 60
        self._runner = runner
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if not self._enabled:
            return False

        if self._thread is not None and self._thread.is_alive():
            return True

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="NotionKnowledgeSyncScheduler",
            daemon=True,
        )
        self._thread.start()
        tray_log(
            "Notion知識の定期同期を開始しました。"
            f" interval_minutes={self._interval_seconds // 60}"
        )
        return True

    def stop(self) -> None:
        self._stop_event.set()

    def run_once(self) -> int:
        creation_flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

        try:
            result = self._runner(
                [
                    str(VENV_PYTHON),
                    str(KNOWLEDGE_SYNC_SCRIPT),
                    "--apply",
                ],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=KNOWLEDGE_SYNC_TIMEOUT_SECONDS,
                creationflags=creation_flags,
            )
        except Exception as error:
            tray_log(
                "Notion知識の定期同期を実行できませんでした。"
                f" type={type(error).__name__}"
            )
            return 1

        if result.returncode == 0:
            tray_log("Notion知識の定期同期が完了しました。")
        else:
            tray_log(
                "Notion知識の定期同期に失敗しました。"
                f" exit_code={result.returncode}"
            )

        return int(result.returncode)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.run_once()

            if self._stop_event.wait(self._interval_seconds):
                return

