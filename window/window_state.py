import json

from core.config import (
    DATA_DIR,
    WINDOW_STATE_FILE,
    DEFAULT_WINDOW_STATE,
    APP_WINDOW_TITLE,
)
from core.logger import window_log
from window.windows_api import (
    get_window_rect_by_title,
    get_virtual_screen_rect,
)


def load_window_state():
    DATA_DIR.mkdir(exist_ok=True)

    if not WINDOW_STATE_FILE.exists():
        window_log("window_state.json が存在しないため、初期値を使用します。")
        return get_safe_default_window_state()

    try:
        with open(WINDOW_STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)

        x = int(state.get("x", DEFAULT_WINDOW_STATE["x"]))
        y = int(state.get("y", DEFAULT_WINDOW_STATE["y"]))
        width = int(state.get("width", DEFAULT_WINDOW_STATE["width"]))
        height = int(state.get("height", DEFAULT_WINDOW_STATE["height"]))

        if width < 400:
            width = DEFAULT_WINDOW_STATE["width"]

        if height < 300:
            height = DEFAULT_WINDOW_STATE["height"]

        loaded_state = {
            "x": x,
            "y": y,
            "width": width,
            "height": height
        }

        loaded_state = clamp_window_size_to_screen(loaded_state)

        window_log(f"ウィンドウ状態を読み込みました: {loaded_state}")

        if not is_window_state_visible_on_screen(loaded_state):
            safe_state = get_safe_default_window_state()
            save_window_state(safe_state)
            return safe_state

        return loaded_state

    except Exception as error:
        window_log(f"ウィンドウ状態の読み込みに失敗しました。初期値を使用します: {error}")
        return get_safe_default_window_state()


def save_window_state(state):
    DATA_DIR.mkdir(exist_ok=True)

    try:
        temp_file = WINDOW_STATE_FILE.with_suffix(".json.tmp")

        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)

        temp_file.replace(WINDOW_STATE_FILE)

        window_log(f"ウィンドウ状態を保存しました: {state}")

        return True

    except Exception as error:
        window_log(f"ウィンドウ状態の保存に失敗しました: {error}")
        return False


def save_current_window_state():
    state = get_window_rect_by_title(APP_WINDOW_TITLE)

    if state is None:
        window_log("現在のウィンドウ状態を取得できなかったため、保存しません。")
        return False

    return save_window_state(state)


def is_window_state_visible_on_screen(state):
    screen_rect = get_virtual_screen_rect()

    if screen_rect is None:
        window_log("画面範囲を取得できないため、保存位置を有効として扱います。")
        return True

    x = state["x"]
    y = state["y"]
    width = state["width"]
    height = state["height"]

    window_left = x
    window_top = y
    window_right = x + width
    window_bottom = y + height

    visible_margin = 100

    is_visible_horizontally = (
        window_right > screen_rect["left"] + visible_margin and
        window_left < screen_rect["right"] - visible_margin
    )

    is_visible_vertically = (
        window_bottom > screen_rect["top"] + visible_margin and
        window_top < screen_rect["bottom"] - visible_margin
    )

    is_visible = is_visible_horizontally and is_visible_vertically

    if is_visible:
        window_log("保存されたウィンドウ位置は現在の画面範囲内です。")
    else:
        window_log("保存されたウィンドウ位置が画面外のため、初期位置に戻します。")
        window_log(f"保存位置: {state}")
        window_log(f"画面範囲: {screen_rect}")

    return is_visible


def get_safe_default_window_state():
    screen_rect = get_virtual_screen_rect()

    if screen_rect is None:
        return DEFAULT_WINDOW_STATE.copy()

    width = DEFAULT_WINDOW_STATE["width"]
    height = DEFAULT_WINDOW_STATE["height"]

    screen_width = screen_rect["width"]
    screen_height = screen_rect["height"]

    if width > screen_width:
        width = max(800, screen_width - 100)

    if height > screen_height:
        height = max(600, screen_height - 100)

    safe_state = {
        "x": 0,
        "y": 0,
        "width": width,
        "height": height
    }

    window_log(f"安全な初期ウィンドウ状態を使用します: {safe_state}")

    return safe_state


def clamp_window_size_to_screen(state):
    screen_rect = get_virtual_screen_rect()

    if screen_rect is None:
        return state

    max_width = max(800, screen_rect["width"] - 100)
    max_height = max(600, screen_rect["height"] - 100)

    if state["width"] > max_width:
        window_log(f"ウィンドウ幅が大きすぎるため補正します: {state['width']} -> {max_width}")
        state["width"] = max_width

    if state["height"] > max_height:
        window_log(f"ウィンドウ高さが大きすぎるため補正します: {state['height']} -> {max_height}")
        state["height"] = max_height

    return state