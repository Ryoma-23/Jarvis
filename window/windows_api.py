import ctypes

from core.logger import window_log


def bring_window_to_front_by_title(title: str) -> bool:
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.FindWindowW(None, title)

        if not hwnd:
            window_log(f"前面表示対象のウィンドウが見つかりません: {title}")
            return False

        SW_RESTORE = 9
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2

        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040

        foreground_hwnd = user32.GetForegroundWindow()
        current_thread_id = kernel32.GetCurrentThreadId()

        foreground_thread_id = user32.GetWindowThreadProcessId(
            foreground_hwnd,
            None
        )

        target_thread_id = user32.GetWindowThreadProcessId(
            hwnd,
            None
        )

        user32.ShowWindow(hwnd, SW_RESTORE)

        user32.AttachThreadInput(
            foreground_thread_id,
            current_thread_id,
            True
        )

        user32.AttachThreadInput(
            target_thread_id,
            current_thread_id,
            True
        )

        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        )

        user32.SetWindowPos(
            hwnd,
            HWND_NOTOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        )

        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
        user32.BringWindowToTop(hwnd)

        user32.AttachThreadInput(
            foreground_thread_id,
            current_thread_id,
            False
        )

        user32.AttachThreadInput(
            target_thread_id,
            current_thread_id,
            False
        )

        window_log("Windows APIでJarvisウィンドウを前面に表示しました。")
        return True

    except Exception as error:
        window_log(f"Windows APIでの前面表示に失敗しました: {error}")
        return False


def get_window_rect_by_title(title: str):
    try:
        user32 = ctypes.windll.user32

        hwnd = user32.FindWindowW(None, title)

        if not hwnd:
            window_log(f"位置取得対象のウィンドウが見つかりません: {title}")
            return None

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()

        success = user32.GetWindowRect(hwnd, ctypes.byref(rect))

        if not success:
            window_log("GetWindowRect に失敗しました。")
            return None

        x = rect.left
        y = rect.top
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        state = {
            "x": x,
            "y": y,
            "width": width,
            "height": height
        }

        window_log(f"現在のウィンドウ状態を取得しました: {state}")

        return state

    except Exception as error:
        window_log(f"Windows APIでのウィンドウ状態取得に失敗しました: {error}")
        return None


def get_virtual_screen_rect():
    try:
        user32 = ctypes.windll.user32

        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        SM_CXVIRTUALSCREEN = 78
        SM_CYVIRTUALSCREEN = 79

        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        rect = {
            "left": x,
            "top": y,
            "right": x + width,
            "bottom": y + height,
            "width": width,
            "height": height
        }

        window_log(f"現在の仮想画面範囲を取得しました: {rect}")

        return rect

    except Exception as error:
        window_log(f"仮想画面範囲の取得に失敗しました: {error}")
        return None