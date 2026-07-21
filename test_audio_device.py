import numpy as np
import sounddevice as sd

from wakeword.audio_device import (
    find_wakeword_input_device,
)


RECORD_SECONDS = 3


def main():
    device = find_wakeword_input_device()

    print("Wake Word用マイクが見つかりました。")
    print(f"デバイス番号: {device.index}")
    print(f"デバイス名: {device.name}")
    print(f"音声API: {device.host_api_name}")
    print(
        f"既定サンプルレート: "
        f"{device.default_sample_rate}"
    )

    sample_rate = device.default_sample_rate
    frame_count = sample_rate * RECORD_SECONDS

    print()
    print("3秒間録音します。")
    print("ReSpeakerへ話しかけてください。")

    audio = sd.rec(
        frames=frame_count,
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=device.index,
    )

    sd.wait()

    peak = int(np.max(np.abs(audio)))
    rms = float(
        np.sqrt(
            np.mean(
                audio.astype(np.float32) ** 2
            )
        )
    )

    print()
    print("録音が完了しました。")
    print(f"最大音量: {peak}")
    print(f"RMS音量: {rms:.2f}")

    if peak == 0:
        raise RuntimeError(
            "音声データがすべて0です。"
            "マイク入力を取得できていません。"
        )

    if peak < 100:
        print(
            "警告: 音量が非常に小さいです。"
            "Windowsのマイク音量を確認してください。"
        )
    else:
        print("ReSpeakerの音声入力を確認できました。")


if __name__ == "__main__":
    main()