import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from core.config import CONTROL_HOST, CONTROL_PORT
from core.logger import window_log
from window.window_state import save_current_window_state


def json_response(handler, status_code, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class _WindowControlHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class WindowControlServer:
    def __init__(
        self,
        controller,
        host=CONTROL_HOST,
        port=CONTROL_PORT,
    ):
        self.controller = controller
        self.host = host
        self.configured_port = port
        self.server = None

    @property
    def port(self):
        if self.server is not None:
            return int(self.server.server_address[1])

        return self.configured_port

    def make_handler(self):
        controller = self.controller

        class ControlRequestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = urlparse(self.path).path

                if path == "/health":
                    json_response(self, 200, {
                        "ok": True,
                        "message": "Jarvis Window control server is running"
                    })
                    return

                if path == "/status":
                    status = controller.get_status()

                    json_response(self, 200, {
                        "ok": True,
                        **status,
                    })
                    return

                if path == "/show":
                    success = controller.show()
                    json_response(self, 200 if success else 500, {
                        "ok": success,
                        "action": "show"
                    })
                    return

                if path == "/focus":
                    success = controller.focus()
                    json_response(self, 200 if success else 500, {
                        "ok": success,
                        "action": "focus"
                    })
                    return

                if path == "/hide":
                    success = controller.hide()
                    json_response(self, 200 if success else 500, {
                        "ok": success,
                        "action": "hide"
                    })
                    return

                if path == "/destroy":
                    success = controller.destroy()
                    json_response(self, 200 if success else 500, {
                        "ok": success,
                        "action": "destroy"
                    })
                    return

                if path == "/save-state":
                    success = save_current_window_state()
                    json_response(self, 200 if success else 500, {
                        "ok": success,
                        "action": "save-state"
                    })
                    return

                json_response(self, 404, {
                    "ok": False,
                    "message": "Not found"
                })

            def do_POST(self):
                path = urlparse(self.path).path

                if path != "/realtime/start":
                    json_response(self, 404, {
                        "ok": False,
                        "message": "Not found",
                    })
                    return

                try:
                    payload = self._read_json()
                    source = str(
                        payload.get("source", "")
                    ).strip()
                    session_id = str(
                        payload.get("session_id", "")
                    ).strip()

                    if not source or not session_id:
                        raise ValueError(
                            "source and session_id are required"
                        )

                    if source != "wakeword":
                        raise ValueError(
                            "source must be wakeword"
                        )

                except ValueError as error:
                    json_response(self, 400, {
                        "ok": False,
                        "message": str(error),
                    })
                    return

                try:
                    accepted = controller.start_realtime(
                        source=source,
                        session_id=session_id,
                    )

                except Exception as error:
                    window_log(
                        "Realtime開始命令の処理中に"
                        f"エラーが発生しました: {error}"
                    )
                    json_response(self, 500, {
                        "ok": False,
                        "message": (
                            "Realtime start command failed"
                        ),
                    })
                    return

                json_response(
                    self,
                    200 if accepted else 409,
                    {
                        "ok": accepted,
                        "accepted": accepted,
                        "action": "realtime-start",
                        "source": source,
                        "session_id": session_id,
                    },
                )

            def _read_json(self):
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

                raw_body = self.rfile.read(content_length)

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

            def log_message(self, format, *args):
                return

        return ControlRequestHandler

    def start(self):
        window_log(
            "Window制御サーバーを起動します: "
            f"http://{self.host}:{self.configured_port}"
        )

        handler = self.make_handler()

        self.server = _WindowControlHTTPServer(
            (self.host, self.configured_port),
            handler
        )

        self.server.serve_forever()

    def stop(self):
        if self.server is None:
            return

        window_log("Window制御サーバーを停止します。")
        self.server.shutdown()
        self.server.server_close()
        self.server = None
