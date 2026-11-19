"""Read-only monitor for active Windows privacy capability use."""
import os
import re

from PyQt6.QtCore import QThread, pyqtSignal


CAPABILITIES = {
    "microphone": "Mikrofon",
    "webcam": "Kamera",
    "location": "Lokalizacja",
    "graphicsCaptureProgrammatic": "Przechwytywanie ekranu",
}


def _friendly_app_name(key_name: str) -> str:
    decoded = key_name.replace("#", "\\")
    exe_match = re.search(r"([^\\/]+\.exe)$", decoded, re.IGNORECASE)
    if exe_match:
        name = os.path.splitext(exe_match.group(1))[0]
    else:
        name = decoded.rsplit("\\", 1)[-1].split("!", 1)[0].split("_", 1)[0]

    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    known_names = {
        "discord": "Discord", "messenger": "Messenger", "teams": "Microsoft Teams",
        "msteams": "Microsoft Teams", "zoom": "Zoom", "skype": "Skype",
        "whatsapp": "WhatsApp", "telegram": "Telegram", "signal": "Signal",
        "slack": "Slack", "webex": "Webex", "obs64": "OBS", "obs32": "OBS",
        "obs": "OBS", "gamebar": "Xbox Game Bar", "snippingtool": "Narzędzie Wycinanie",
        "msedge": "Microsoft Edge", "chrome": "Google Chrome", "firefox": "Firefox",
    }
    return known_names.get(normalized, name or "Nieznana aplikacja")


def _active_apps_for_capability(capability: str) -> list[str]:
    """Reads Windows' current-use timestamps; does not request device access."""
    try:
        import winreg
    except ImportError:
        return []

    base_path = rf"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\{capability}"
    active_apps = set()

    def walk(key, key_name: str, depth: int = 0):
        if depth > 4:
            return
        try:
            start, _ = winreg.QueryValueEx(key, "LastUsedTimeStart")
            stop, _ = winreg.QueryValueEx(key, "LastUsedTimeStop")
            if int(start) > 0 and (int(stop) == 0 or int(start) > int(stop)):
                if key_name and key_name.lower() not in {"nonpackaged", "packaged", "consentstore"}:
                    active_apps.add(_friendly_app_name(key_name))
        except (OSError, TypeError, ValueError):
            pass

        try:
            child_names = [winreg.EnumKey(key, i) for i in range(winreg.QueryInfoKey(key)[0])]
        except OSError:
            return
        for child_name in child_names:
            try:
                with winreg.OpenKey(key, child_name, 0, winreg.KEY_READ) as child:
                    walk(child, child_name, depth + 1)
            except OSError:
                continue

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base_path, 0, winreg.KEY_READ) as root:
            walk(root, "")
    except OSError:
        return []
    return sorted(active_apps, key=str.casefold)


def read_privacy_activity() -> dict[str, list[str]]:
    result = {"microphone": [], "camera": [], "location": [], "screen": []}
    for capability, display_key in CAPABILITIES.items():
        apps = _active_apps_for_capability(capability)
        if display_key == "Mikrofon":
            result["microphone"] = sorted(set(result["microphone"] + apps), key=str.casefold)
        elif display_key == "Kamera":
            result["camera"] = sorted(set(result["camera"] + apps), key=str.casefold)
        elif display_key == "Lokalizacja":
            result["location"] = sorted(set(result["location"] + apps), key=str.casefold)
        else:
            result["screen"] = sorted(set(result["screen"] + apps), key=str.casefold)
    return result


class PrivacyMonitorWorker(QThread):
    """Polls the Windows privacy activity registry and emits changes."""
    activity_changed = pyqtSignal(dict)

    def run(self):
        previous = None
        while not self.isInterruptionRequested():
            try:
                current = read_privacy_activity()
                if current != previous:
                    self.activity_changed.emit(current)
                    previous = current
            except Exception:
                pass
            self.msleep(900)

    def stop(self):
        self.requestInterruption()
        self.wait(1500)
