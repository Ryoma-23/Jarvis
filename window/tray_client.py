import json
import time
import urllib.error
import urllib.request

from core.config import (
    TRAY_REALTIME_BRIDGE_URL,
    WINDOW_CLOSE_REALTIME_NOTIFY_RETRY_COUNT,
    WINDOW_CLOSE_REALTIME_NOTIFY_RETRY_DELAY_SECONDS,
    WINDOW_CLOSE_REALTIME_NOTIFY_TIMEOUT_SECONDS,
)
from core.logger import window_log


def notify_realtime_finished(
    reason: str,
    session_id: str,
    retry_count: int = (
        WINDOW_CLOSE_REALTIME_NOTIFY_RETRY_COUNT
    ),
    retry_delay: float = (
        WINDOW_CLOSE_REALTIME_NOTIFY_RETRY_DELAY_SECONDS
    ),
    timeout: float = (
        WINDOW_CLOSE_REALTIME_NOTIFY_TIMEOUT_SECONDS
    ),
) -> bool:
    """
    Window終了後、TrayへRealtime終了を通知する。

    JavaScriptのsendBeaconが失敗した場合の
    session-awareなフォールバックとして使用する。
    """

    normalized_reason = str(reason).strip()
    normalized_session_id = str(session_id).strip()

    if not normalized_reason or not normalized_session_id:
        return False

    payload = json.dumps(
        {
            "reason": normalized_reason,
            "session_id": normalized_session_id,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    attempts = max(1, int(retry_count))

    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            (
                f"{TRAY_REALTIME_BRIDGE_URL}"
                "/realtime/finished"
            ),
            data=payload,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
            ) as response:
                response_data = json.loads(
                    response.read().decode("utf-8")
                )
                return (
                    response.status == 200
                    and response_data.get("accepted") is True
                )

        except urllib.error.HTTPError as error:
            if error.code == 409:
                window_log(
                    "TrayのRealtime終了処理は"
                    "すでに完了しています。"
                    f" session_id={normalized_session_id}"
                )
                return True

            window_log(
                "TrayへのRealtime終了通知が"
                "HTTPエラーになりました。"
                f" attempt={attempt}/{attempts},"
                f" status={error.code},"
                f" session_id={normalized_session_id}"
            )

            if error.code < 500 or attempt >= attempts:
                return False

            time.sleep(retry_delay)

        except Exception as error:
            window_log(
                "TrayへのRealtime終了通知に失敗しました。"
                f" attempt={attempt}/{attempts},"
                f" session_id={normalized_session_id} / {error}"
            )

            if attempt < attempts:
                time.sleep(retry_delay)

    return False
