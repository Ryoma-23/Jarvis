import time

from collections.abc import Callable
from typing import TypeVar

from app.integrations.notion_client import (
    NotionConnectionError,
    NotionRateLimitError,
    NotionServerError,
)
from app.integrations.openai_embedding_client import EmbeddingAPIError
from app.vector.chroma_index import ChromaIndexError


_T = TypeVar("_T")


def run_with_sync_retry(
    operation: Callable[[], _T],
    *,
    attempts: int,
    sleeper: Callable[[float], None] = time.sleep,
) -> _T:
    if attempts < 1:
        raise ValueError("attemptsは1以上が必要です。")

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except (
            NotionConnectionError,
            NotionRateLimitError,
            NotionServerError,
            EmbeddingAPIError,
            ChromaIndexError,
        ) as error:
            if attempt >= attempts:
                raise

            sleeper(sync_retry_delay(error, attempt))

    raise RuntimeError("Notion知識同期の再試行に失敗しました。")


def sync_retry_delay(error: Exception, attempt: int) -> float:
    if isinstance(error, NotionRateLimitError):
        try:
            retry_after = float(error.retry_after or "")
        except ValueError:
            retry_after = 0.0

        if retry_after > 0:
            return min(retry_after, 60.0)

    return min(float(2 ** (attempt - 1)), 30.0)

