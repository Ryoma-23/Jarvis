import sounddevice as sd


def main():
    devices = sd.query_devices()

    print("利用可能な音声デバイス\n")

    for index, device in enumerate(devices):
        input_channels = device["max_input_channels"]

        if input_channels > 0:
            print(
                f"{index}: {device['name']} "
                f"(入力チャンネル: {input_channels})"
            )


if __name__ == "__main__":
    main()