import json
import threading
from collections.abc import Callable
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from urllib.parse import urlparse


class TrayRealtimeBridge:
    """
    WindowプロセスからTrayプロセスへ
    Realtime状態を通知するための
    ローカルHTTPサーバー。
    """

    def __init__(
        self,
        on_starting: Callable[[str], None],
        on_started: Callable[[str], None],
        on_finished: Callable[[str], None],
        host: str = "127.0.0.1",
        port: int = 8767,
    ) -> None:
        self._on_starting = on_starting
        self._on_started = on_started
        self._on_finished = on_finished

        self._host = host
        self._port = port

        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return

        handler_class = self._create_handler()

        self._server = ThreadingHTTPServer(
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
            f"http://{self._host}:{self._port} "
            "で起動しました。"
        )

    def stop(self) -> None:
        server = self._server
        self._server = None

        if server is None:
            return

        server.shutdown()
        server.server_close()

        if self._thread is not None:
            self._thread.join(timeout=3.0)

        self._thread = None

        print(
            "[TrayRealtimeBridge] "
            "終了しました。"
        )

    def _create_handler(
        self,
    ) -> type[BaseHTTPRequestHandler]:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
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

            def do_POST(self) -> None:
                path = urlparse(self.path).path
                payload = self._read_json()

                try:
                    if path == "/realtime/starting":
                        source = str(
                            payload.get(
                                "source",
                                "unknown",
                            )
                        )

                        bridge._on_starting(source)

                        self._send_json(
                            200,
                            {"ok": True},
                        )
                        return

                    if path == "/realtime/started":
                        source = str(
                            payload.get(
                                "source",
                                "unknown",
                            )
                        )

                        bridge._on_started(source)

                        self._send_json(
                            200,
                            {"ok": True},
                        )
                        return

                    if path == "/realtime/finished":
                        reason = str(
                            payload.get(
                                "reason",
                                "unknown",
                            )
                        )

                        bridge._on_finished(reason)

                        self._send_json(
                            200,
                            {"ok": True},
                        )
                        return

                    self._send_json(
                        404,
                        {
                            "ok": False,
                            "message": "Not found",
                        },
                    )

                except Exception as error:
                    self._send_json(
                        500,
                        {
                            "ok": False,
                            "error": str(error),
                        },
                    )

            def _read_json(self) -> dict:
                content_length = int(
                    self.headers.get(
                        "Content-Length",
                        "0",
                    )
                )

                if content_length <= 0:
                    return {}

                raw_body = self.rfile.read(
                    content_length
                )

                try:
                    return json.loads(
                        raw_body.decode("utf-8")
                    )

                except json.JSONDecodeError:
                    return {}

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
                self.end_headers()
                self.wfile.write(body)

            def log_message(
                self,
                format: str,
                *args,
            ) -> None:
                return

        return Handler