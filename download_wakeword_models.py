import openwakeword


def main():
    print("openWakeWordモデルをダウンロードします。")

    openwakeword.utils.download_models()

    print("モデルのダウンロードが完了しました。")


if __name__ == "__main__":
    main()