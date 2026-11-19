"""
Obsługa autostartu z systemem Windows przez rejestr (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run).
Nie wymaga uprawnień administratora.
"""
import os
import sys
import winreg

APP_NAME = "FloatingIsland"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_launch_command() -> str:
    """Zwraca pełną ścieżkę do bezokienkowego uruchomienia przez pythonw.exe."""
    python_dir = os.path.dirname(sys.executable)
    pythonw_path = os.path.join(python_dir, "pythonw.exe")
    if not os.path.exists(pythonw_path):
        pythonw_path = sys.executable

    # Ścieżka do pliku main.py na Pulpicie
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    main_py_path = os.path.join(project_dir, "main.py")

    return f'"{pythonw_path}" "{main_py_path}"'


def is_autostart_enabled() -> bool:
    """Sprawdza, czy aplikacja jest dodana do autostartu."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception as err:
        print(f"[Autostart Error] {err}")
        return False


def set_autostart(enabled: bool) -> bool:
    """Włącza lub wyłącza autostart w rejestrze Windows."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                cmd = get_launch_command()
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception as err:
        print(f"[Autostart Error] Nie udało się zmienić rejestru: {err}")
        return False
