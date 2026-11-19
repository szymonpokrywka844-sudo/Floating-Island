"""
Menedżer motywów (Theme Manager) dla Floating Island.
Obsługuje motywy: Ciemny (Dark OLED), Jasny (Light macOS style) oraz Systemowy (zgodny z Windows).
Automatycznie wykrywa zmiany motywu w rejestrze systemu Windows.
"""
import winreg
from PyQt6.QtCore import QObject, pyqtSignal, QSettings, QTimer
from PyQt6.QtGui import QColor


class ThemeManager(QObject):
    """Zarządza motywami wizualnymi wyspy i emituje sygnał theme_changed."""
    theme_changed = pyqtSignal(str)

    THEME_DARK = "dark"
    THEME_LIGHT = "light"
    THEME_SYSTEM = "system"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("FloatingIsland", "FloatingIsland")
        self._mode = self.settings.value("theme_mode", self.THEME_DARK)

        # Sprawdzanie zmian motywu Windows w trybie systemowym
        self._last_system_is_light = self._read_windows_theme()
        self.sys_timer = QTimer(self)
        self.sys_timer.timeout.connect(self._check_windows_theme_change)
        self.sys_timer.start(2500)

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, val: str):
        if val in (self.THEME_DARK, self.THEME_LIGHT, self.THEME_SYSTEM):
            self._mode = val
            self.settings.setValue("theme_mode", val)
            self.settings.sync()
            self.theme_changed.emit(self.effective_theme)

    @property
    def effective_theme(self) -> str:
        """Zwraca rzeczywisty motyw: 'dark' lub 'light'."""
        if self._mode == self.THEME_SYSTEM:
            return self.THEME_LIGHT if self._read_windows_theme() else self.THEME_DARK
        return self._mode

    @property
    def is_dark(self) -> bool:
        return self.effective_theme == self.THEME_DARK

    def _read_windows_theme(self) -> bool:
        """Zwraca True jeśli system Windows używa jasnego motywu aplikacji."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                0, winreg.KEY_READ
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return val == 1
        except Exception:
            return False

    def _check_windows_theme_change(self):
        """Wykrywa zmianę motywu w Windows w czasie rzeczywistym."""
        if self._mode == self.THEME_SYSTEM:
            current_is_light = self._read_windows_theme()
            if current_is_light != self._last_system_is_light:
                self._last_system_is_light = current_is_light
                self.theme_changed.emit(self.effective_theme)

    # --- Paleta kolorów ---
    @property
    def bg_color(self) -> QColor:
        """Główne tło kapsułki wyspy."""
        if self.is_dark:
            return QColor(14, 14, 16, 248)
        else:
            return QColor(246, 246, 248, 250)

    @property
    def border_color(self) -> QColor:
        """Krawędź 1px wokół wyspy."""
        if self.is_dark:
            return QColor(255, 255, 255, 28)
        else:
            return QColor(0, 0, 0, 38)

    @property
    def glow_color(self) -> QColor:
        """Miękka poświata pod spodem."""
        if self.is_dark:
            return QColor(0, 0, 0, 85)
        else:
            return QColor(0, 0, 0, 45)

    @property
    def text_primary(self) -> str:
        return "#FFFFFF" if self.is_dark else "#1A1A1C"

    @property
    def text_secondary(self) -> str:
        return "#8E8E93" if self.is_dark else "#6C6C70"

    @property
    def card_bg(self) -> str:
        return "#242426" if self.is_dark else "#E5E5EB"

    @property
    def card_border(self) -> str:
        return "#38383A" if self.is_dark else "#D1D1D8"

    @property
    def hover_bg(self) -> str:
        return "#343438" if self.is_dark else "#D8D8DE"

    @property
    def accent_color(self) -> str:
        return "#0A84FF" if self.is_dark else "#007AFF"

    @property
    def eyes_color(self) -> str:
        return "#FFFFFF" if self.is_dark else "#1A1A1C"


# Globalna instancja singleton
theme_manager = ThemeManager()
