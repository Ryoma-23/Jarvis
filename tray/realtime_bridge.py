import json
import threading
from collections.abc import Callable
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from urllib.parse import urlparse

from core.config import (
    SERVER_URL,
    TRAY_REALTIME_BRIDGE_HOST,
    TRAY_REALTIME_BRIDGE_PORT,
)


RealtimeLifecycleCallback = Callable[
    [str, str],
    bool | None,
]


class _TrayRealtimeHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class TrayRealtimeBridge:
    """
    WindowプロセスからTrayプロセスへ
    Realtime状態を通知するための
    ローカルHTTPサーバー。
    """

    def __init__(
        self,
        on_starting: RealtimeLifecycleCallback,
        on_started: RealtimeLifecycleCallback,
        on_finished: RealtimeLifecycleCallback,
        host: str = TRAY_REALTIME_BRIDGE_HOST,
        port: int = TRAY_REALTIME_BRIDGE_PORT,
        allowed_origin: str = SERVER_URL,
    ) -> None:
        self._on_starting = on_starting
        self._on_started = on_started
        self._on_finished = on_finished

        self._host = host
        self._port = port
        self._allowed_origin = allowed_origin

        self._server: _TrayRealtimeHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._server is not None:
            return int(self._server.server_address[1])

        return self._port

    @property
    def is_running(self) -> bool:
        return (
            self._server is not None
            and self._thread is not None
            and self._thread.is_alive()
        )

    def start(self) -> bool:
        if self.is_running:
            return False

        if self._server is not None:
            self.stop()

        handler_class = self._create_handler()

        self._server = _TrayRealtimeHTTPServer(
            (self._host, self._port),
            handler_class,
        )

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="TrayRealtimeBridge",
            daemon=True,
        )

        self._thread.start()

        print(
            "[TrayRealtimeBridge] "
            f"http://{self._host}:{self.port} "
            "で起動しました。"
        )
        return True

    def stop(self) -> bool:
        server = self._server
        self._server = None

        if server is None:
            return False

        server.shutdown()
        server.server_close()

        if self._thread is not None:
            self._thread.join(timeout=3.0)

        self._thread = None

        print(
            "[TrayRealtimeBridge] "
            "終了しました。"
        )
        return True

    def _create_handler(
        self,
    ) -> type[BaseHTTPRequestHandler]:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            _REALTIME_PATHS = {
                "/realtime/starting",
                "/realtime/started",
                "/realtime/finished",
            }

            def do_GET(self) -> None:
                path = urlparse(self.path).path

                if path == "/health":
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "service": (
                                "tray-realtime-bridge"
                            ),
                        },
                    )
                    return

                self._send_json(
                    404,
                    {
                        "ok": False,
                        "message": "Not found",
                    },
                )

            def do_OPTIONS(self) -> None:
                path = urlparse(self.path).path

                if path not in self._REALTIME_PATHS:
                    self._send_json(
                        404,
                        {
                            "ok": False,
                            "message": "Not found",
                        },
                    )
                    return

                if not self._origin_is_allowed():
                    self._send_json(
                        403,
                        {
                            "ok": False,
                            "message": "Origin not allowed",
                        },
                    )
                    return

                self.send_response(204)
                self._send_cors_headers()
                self.send_header(
                    "Access-Control-Allow-Methods",
                    "POST, OPTIONS",
                )
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Content-Type",
                )
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self) -> None:
                path = urlparse(self.path).path

                if path not in self._REALTIME_PATHS:
                    self._send_json(
                        404,
                        {
                            "ok": False,
                            "message": "Not found",
                        },
                    )
                    return

                try:
                    payload = self._read_json()

                    if not self._origin_is_allowed():
                        self._send_json(
                            403,
                            {
                                "ok": False,
                                "message": "Origin not allowed",
                            },
                        )
                        return

                    session_id = self._required_text(
                        payload,
                        "session_id",
                    )

                    if path == "/realtime/starting":
                        source = self._optional_text(
                            payload,
                            "source",
                            "unknown",
                        )

                        self._send_callback_result(
                            bridge._on_starting(
                                source,
                                session_id,
                            ),
                            session_id,
                        )
                        return

                    if path == "/realtime/started":
                        source = self._optional_text(
                            payload,
                            "source",
                            "unknown",
                        )

                        self._send_callback_result(
                            bridge._on_started(
                                source,
                                session_id,
                            ),
                            session_id,
                        )
                        return

                    if path == "/realtime/finished":
                        reason = self._optional_text(
                            payload,
                            "reason",
                            "unknown",
                        )

                        self._send_callback_result(
                            bridge._on_finished(
                                reason,
                                session_id,
                            ),
                            session_id,
                        )
                        return

                except ValueError as error:
                    self._send_json(
                        400,
                        {
                            "ok": False,
                            "message": str(error),
                        },
                    )

                except Exception as error:
                    print(
                        "[TrayRealtimeBridge] "
                        "通知処理でエラーが発生しました。 "
                        f"{type(error).__name__}: {error}"
                    )
                    self._send_json(
                        500,
                        {
                            "ok": False,
                            "message": (
                                "Realtime lifecycle callback failed"
                            ),
                        },
                    )

            def _read_json(self) -> dict:
                try:
                    content_length = int(
                        self.headers.get(
                            "Content-Length",
                            "0",
                        )
                    )

                except ValueError as error:
                    raise ValueError(
                        "Invalid Content-Length"
                    ) from error

                if content_length <= 0:
                    raise ValueError(
                        "JSON body is required"
                    )

                if content_length > 16 * 1024:
                    raise ValueError(
                        "JSON body is too large"
                    )

                raw_body = self.rfile.read(
                    content_length
                )

                try:
                    payload = json.loads(
                        raw_body.decode("utf-8")
                    )

                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                ) as error:
                    raise ValueError(
                        "Invalid JSON body"
                    ) from error

                if not isinstance(payload, dict):
                    raise ValueError(
                        "JSON body must be an object"
                    )

                return payload

            def _required_text(
                self,
                payload: dict,
                name: str,
            ) -> str:
                value = str(payload.get(name, "")).strip()

                if not value:
                    raise ValueError(
                        f"{name} is required"
                    )

                return value

            def _optional_text(
                self,
                payload: dict,
                name: str,
                default: str,
            ) -> str:
                value = str(
                    payload.get(name, default)
                ).strip()
                return value or default

            def _send_callback_result(
                self,
                result: bool | None,
                session_id: str,
            ) -> None:
                accepted = result is not False

                self._send_json(
                    200 if accepted else 409,
                    {
                        "ok": accepted,
                        "accepted": accepted,
                        "session_id": session_id,
                    },
                )

            def _origin_is_allowed(self) -> bool:
                origin = self.headers.get("Origin")
                return (
                    origin is None
                    or origin == bridge._allowed_origin
                )

            def _send_cors_headers(self) -> None:
                origin = self.headers.get("Origin")

                if origin == bridge._allowed_origin:
                    self.send_header(
                        "Access-Control-Allow-Origin",
                        origin,
                    )
                    self.send_header("Vary", "Origin")

            def _send_json(
                self,
                status: int,
                data: dict,
            ) -> None:
                body = json.dumps(
                    data,
                    ensure_ascii=False,
                ).encode("utf-8")

                self.send_response(status)
                self.send_header(
                    "Content-Type",
                    "application/json; charset=utf-8",
                )
                self.send_header(
                    "Content-Length",
                    str(len(body)),
                )
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(body)

            def log_message(
                self,
                format: str,
                *args,
            ) -> None:
                return

        return Handler
