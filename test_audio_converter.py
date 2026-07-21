import numpy as np

from wakeword.audio_converter import (
    convert_sample_rate,
)


def main():
    source_sample_rate = 48000
    target_sample_rate = 16000

    # 80ms分
    source_samples = int(
        source_sample_rate * 0.08
    )

    audio = np.zeros(
        source_samples,
        dtype=np.int16,
    )

    converted = convert_sample_rate(
        audio=audio,
        source_sample_rate=source_sample_rate,
        target_sample_rate=target_sample_rate,
    )

    print(f"変換前: {len(audio)} samples")
    print(f"変換後: {len(converted)} samples")

    assert len(audio) == 3840
    assert len(converted) == 1280

    print("サンプルレート変換成功")


if __name__ == "__main__":
    main()