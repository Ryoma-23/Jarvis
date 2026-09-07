import json
import os
import time
import uuid

from pathlib import Path

from app.config import NOTION_KNOWLEDGE_SYNC_LOCK_FILE


DEFAULT_STALE_LOCK_SECONDS = 6 * 60 * 60


class KnowledgeSyncAlreadyRunningError(RuntimeError):
    """Raised when another knowledge synchronization owns the lock."""


class KnowledgeSyncLock:
    def __init__(
        self,
        path: str | Path = NOTION_KNOWLEDGE_SYNC_LOCK_FILE,
        *,
        stale_after_seconds: int = DEFAULT_STALE_LOCK_SECONDS,
    ):
        self.path = Path(path)
        self._stale_after_seconds = stale_after_seconds
        self._token = uuid.uuid4().hex
        self._acquired = False

    def __enter__(self) -> "KnowledgeSyncLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()

    def acquire(self) -> None:
        if self._acquired:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(2):
            try:
                descriptor = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                if attempt == 0 and self._is_stale():
                    try:
                        self.path.unlink()
                    except OSError:
                        pass
                    continue

                raise KnowledgeSyncAlreadyRunningError(
                    "Notion知識同期は既に実行中です。"
                ) from None

            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "pid": os.getpid(),
                        "token": self._token,
                        "created_at": time.time(),
                    },
                    file,
                )

            self._acquired = True
            return

        raise KnowledgeSyncAlreadyRunningError(
            "Notion知識同期のロックを取得できませんでした。"
        )

    def release(self) -> None:
        if not self._acquired:
            return

        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            data = None

        if isinstance(data, dict) and data.get("token") == self._token:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass

        self._acquired = False

    def _is_stale(self) -> bool:
        created_at = None

        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if isinstance(data, dict):
                value = data.get("created_at")

                if isinstance(value, (int, float)) and not isinstance(
                    value,
                    bool,
                ):
                    created_at = float(value)
        except (OSError, json.JSONDecodeError):
            pass

        try:
            reference_time = (
                created_at
                if created_at is not None
                else self.path.stat().st_mtime
            )
            age = time.time() - reference_time
        except OSError:
            return False

        return age >= self._stale_after_seconds
