import openwakeword


def main():
    print("openWakeWordモデルをダウンロードします。")

    openwakeword.utils.download_models()

    from core.config import WAKEWORD_KEYWORD_MODEL_DIR
    from wakeword.keyword_detector import prepare_model

    print("追加フレーズ用sherpa-onnxモデルを準備します。")
    prepare_model(WAKEWORD_KEYWORD_MODEL_DIR)
    print("モデルのダウンロードが完了しました。")


if __name__ == "__main__":
    main()