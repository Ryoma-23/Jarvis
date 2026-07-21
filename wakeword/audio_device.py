from dataclasses import dataclass

import sounddevice as sd

from core.config import (
    WAKEWORD_DEVICE_NAME,
    WAKEWORD_HOST_API_NAME,
)


@dataclass(frozen=True)
class AudioInputDevice:
    index: int
    name: str
    host_api_name: str
    input_channels: int
    default_sample_rate: int


def find_wakeword_input_device() -> AudioInputDevice:
    """
    ReSpeaker + Windows WASAPIに一致する入力デバイスを検索する。

    sounddeviceのデバイス番号は固定値ではないため、
    番号ではなくデバイス名とHost API名で検索する。
    """

    devices = sd.query_devices()
    host_apis = sd.query_hostapis()

    target_device_name = WAKEWORD_DEVICE_NAME.lower()
    target_host_api_name = WAKEWORD_HOST_API_NAME.lower()

    candidates: list[AudioInputDevice] = []

    for device_index, device in enumerate(devices):
        input_channels = int(device["max_input_channels"])

        if input_channels <= 0:
            continue

        host_api_index = int(device["hostapi"])
        host_api = host_apis[host_api_index]

        device_name = str(device["name"])
        host_api_name = str(host_api["name"])

        name_matches = (
            target_device_name in device_name.lower()
        )

        host_api_matches = (
            target_host_api_name in host_api_name.lower()
        )

        if not name_matches or not host_api_matches:
            continue

        candidates.append(
            AudioInputDevice(
                index=device_index,
                name=device_name,
                host_api_name=host_api_name,
                input_channels=input_channels,
                default_sample_rate=int(
                    float(device["default_samplerate"])
                ),
            )
        )

    if not candidates:
        raise RuntimeError(
            "Wake Word用ReSpeakerが見つかりません。"
            f" device_name={WAKEWORD_DEVICE_NAME},"
            f" host_api={WAKEWORD_HOST_API_NAME}"
        )

    # 同条件のデバイスが複数ある場合は、
    # 入力チャンネル数が多いものを優先する。
    candidates.sort(
        key=lambda candidate: candidate.input_channels,
        reverse=True,
    )

    return candidates[0]