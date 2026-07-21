import math

import numpy as np
from scipy.signal import resample_poly


def convert_sample_rate(
    audio: np.ndarray,
    source_sample_rate: int,
    target_sample_rate: int,
) -> np.ndarray:
    """
    int16 PCM音声を指定サンプルレートへ変換する。
    """

    if source_sample_rate <= 0:
        raise ValueError(
            "source_sample_rateは正の値である必要があります。"
        )

    if target_sample_rate <= 0:
        raise ValueError(
            "target_sample_rateは正の値である必要があります。"
        )

    mono_audio = np.asarray(
        audio,
        dtype=np.int16,
    ).reshape(-1)

    if source_sample_rate == target_sample_rate:
        return mono_audio.copy()

    greatest_common_divisor = math.gcd(
        source_sample_rate,
        target_sample_rate,
    )

    up = target_sample_rate // greatest_common_divisor
    down = source_sample_rate // greatest_common_divisor

    converted = resample_poly(
        mono_audio.astype(np.float32),
        up=up,
        down=down,
    )

    converted = np.clip(
        converted,
        -32768,
        32767,
    )

    return converted.astype(np.int16)