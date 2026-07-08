import sys
import urllib.request
import webview


HOST = "127.0.0.1"
PORT = 8000
SERVER_URL = f"http://{HOST}:{PORT}"


def is_server_alive() -> bool:
    try:
        with urllib.request.urlopen(SERVER_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def main():
    if not is_server_alive():
        print("Jarvisサーバーが起動していません。")
        sys.exit(1)

    window = webview.create_window(
        title="J.A.R.V.I.S",
        url=SERVER_URL,
        width=1100,
        height=850,
        resizable=True,
        fullscreen=False,
        confirm_close=False,
    )

    webview.start()


if __name__ == "__main__":
    main()