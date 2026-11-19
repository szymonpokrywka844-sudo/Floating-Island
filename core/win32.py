"""
Niskopoziomowe API Windows (C / ctypes) do integracji z powłoką DWM
oraz detekcji gier i aplikacji w trybie pełnoekranowym (Fullscreen Mode).
"""
import ctypes
from ctypes import wintypes

# Stałe DWM i Win32
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000


def apply_window_tweaks(hwnd: int) -> bool:
    """
    Konfiguruje okno jako ToolWindow (brak ikony na pasku zadań)
    oraz wymusza zaokrąglenie rogów Windows 11 DWM.
    """
    try:
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi

        # 1. Wymuszenie zaokrąglonych rogów w systemie Windows 11
        preference = ctypes.c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference)
        )

        # 2. Ukrycie z paska zadań i włączenie obsługi warstw przezroczystości
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_TOOLWINDOW | WS_EX_LAYERED)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

        return True
    except Exception as err:
        print(f"[Win32 Warning] Nie udało się zaaplikować stylu: {err}")
        return False


def is_fullscreen_active(screen_rect, our_hwnd: int) -> bool:
    """
    Sprawdza, czy na danym monitorze aktywna jest gra lub aplikacja w pełnym ekranie
    (DirectX/Vulkan game, YouTube fullscreen, VLC, F11 browser).
    Zwykłe zmaksymalizowane okna z widocznym paskiem zadań NIE są traktowane jako fullscreen.
    """
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        
        # Jeśli brak aktywnego okna lub aktywna jest nasza wyspa -> nie chowaj
        if not hwnd or hwnd == our_hwnd:
            return False

        # Ignoruj Pulpit Windows oraz pasek zadań
        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buf, 256)
        cname = class_buf.value
        if cname in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return False

        # Pobierz współrzędne aktywnego okna
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False

        w_left, w_top, w_right, w_bottom = rect.left, rect.top, rect.right, rect.bottom

        s_x = screen_rect.x()
        s_y = screen_rect.y()
        s_w = screen_rect.width()
        s_h = screen_rect.height()

        # Okno jest w trybie pełnoekranowym na tym monitorze, jeśli pokrywa CAŁY monitor
        # łącznie z obszarem paska zadań (zarówno gry, jak i filmy fullscreen)
        is_fs = (
            w_left <= s_x and
            w_top <= s_y and
            w_right >= (s_x + s_w) and
            w_bottom >= (s_y + s_h)
        )
        return is_fs
    except Exception:
        return False
