"""
Domyślny moduł zegara i statusu systemu.
"""
from PyQt6.QtCore import QTimer, QTime
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from modules.base import BaseModule


class ClockModule(BaseModule):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.time_label = None
        self.mini_status = None
        
        # Zegar tykający co sekundę
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_time)
        self.timer.start(1000)

    def get_pill_widget(self, parent: QWidget) -> QWidget:
        widget = QWidget(parent)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Zielona kropka gotowości
        dot = QLabel("●", widget)
        dot.setStyleSheet("color: #FFFFFF; font-size: 10px;")

        # Etykieta czasu
        self.time_label = QLabel(self._get_current_time_str(), widget)
        self.time_label.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 13px;")

        # Status
        self.mini_status = QLabel("Wyspa gotowa", widget)
        self.mini_status.setStyleSheet("color: #8E8E93; font-size: 11px;")

        layout.addWidget(dot)
        layout.addWidget(self.time_label)
        layout.addStretch()
        layout.addWidget(self.mini_status)
        return widget

    def get_expanded_widget(self, parent: QWidget) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 8, 4, 4)

        title = QLabel("Dynamic Island • Windows", widget)
        title.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold;")

        desc = QLabel(
            "Wyspa działa modułowo.\n"
            "Każdy moduł jest osobnym plikiem w folderze /modules.",
            widget
        )
        desc.setStyleSheet("color: #A1A1A6; font-size: 12px;")

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch()
        return widget

    def _get_current_time_str(self) -> str:
        return QTime.currentTime().toString("HH:mm")

    def _update_time(self):
        if self.time_label:
            self.time_label.setText(self._get_current_time_str())
