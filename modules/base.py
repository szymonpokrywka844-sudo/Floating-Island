"""
Klasa bazowa dla modułów pływającej wyspy.
Każdy nowy moduł dziedziczy po BaseModule i dostarcza widgety dla widoku pigułki oraz rozwiniętego.
"""
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget


class BaseModule(QObject):
    # Sygnał, gdy moduł chce wymusić rozszerzenie lub zwinięcie wyspy
    request_expand = pyqtSignal()
    request_collapse = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def get_pill_widget(self, parent: QWidget) -> QWidget:
        """Zwraca mały widget wyświetlany w stanie zwiniętym."""
        raise NotImplementedError

    def get_expanded_widget(self, parent: QWidget) -> QWidget:
        """Zwraca pełny panel wyświetlany po rozwinięciu wyspy."""
        raise NotImplementedError

    def on_expand(self):
        """Wywoływane, gdy wyspa się rozwija."""
        pass

    def on_collapse(self):
        """Wywoływane, gdy wyspa się zwija."""
        pass
