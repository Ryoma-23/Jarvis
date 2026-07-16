import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.config import CONTROL_HOST, CONTROL_PORT, CONTROL_URL
from core.logger import window_log
from window.window_state import save_current_window_state


def json_response(handler, status_code, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class WindowControlServer:
    def __init__(self, controller):
        self.controller = controller
        self.server = None

    def make_handler(self):
        controller = self.controller

        class ControlRequestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/health":
                    json_response(self, 200, {
                        "ok": True,
                        "message": "Jarvis Window control server is running"
                    })
                    return

                if self.path == "/status":
                    status = controller.get_status()

                    json_response(self, 200, {
                        "ok": True,
                        **status,
                    })
                    return

                if self.path == "/show":
                    success = controller.show()
                    json_response(self, 200 if success else 500, {
                        "ok": success,
                        "action": "show"
                    })
                    return

                if self.path == "/focus":
                    success = controller.focus()
                    json_response(self, 200 if success else 500, {
                        "ok": success,
                        "action": "focus"
                    })
                    return

                if self.path == "/hide":
                    success = controller.hide()
                    json_response(self, 200 if success else 500, {
                        "ok": success,
                        "action": "hide"
                    })
                    return

                if self.path == "/destroy":
                    success = controller.destroy()
                    json_response(self, 200 if success else 500, {
                        "ok": success,
                        "action": "destroy"
                    })
                    return

                if self.path == "/save-state":
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

            def log_message(self, format, *args):
                return

        return ControlRequestHandler

    def start(self):
        window_log(f"Window制御サーバーを起動します: {CONTROL_URL}")

        handler = self.make_handler()

        self.server = ThreadingHTTPServer(
            (CONTROL_HOST, CONTROL_PORT),
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