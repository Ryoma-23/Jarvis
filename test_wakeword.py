import time

from wakeword.wakeword_listener import (
    WakeWordListener,
)


def on_wakeword_detected(score: float) -> None:
    print("================================")
    print("Wake Word検知成功")
    print(f"score: {score:.3f}")
    print("================================")
    print()
    print(
        "5秒後にWake Word待機を再開します。"
    )

    # 単体テストなので、
    # Realtime会話の代わりに5秒待機する。
    time.sleep(5)

    listener.resume()


listener = WakeWordListener(
    on_detected=on_wakeword_detected
)


def main() -> None:
    listener.start()

    print()
    print("Ctrl+Cで終了します。")
    print()

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print()
        print("終了操作を受け付けました。")
        listener.stop()


if __name__ == "__main__":
    main()