"""
Moduł Drop Shelf (Półka na przeciągane pliki w stylu macOS Yoink / Dropover).
Pozwala upuszczać pliki na wyspę, przechowywać je i przeciągać do innych aplikacji.
"""
import os
from PyQt6.QtCore import Qt, QUrl, QMimeData, QPoint, pyqtSignal
from PyQt6.QtGui import QDrag, QPainter, QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, 
    QScrollArea, QApplication, QFrame
)
from core.theme import theme_manager


def format_file_size(size_bytes: int) -> str:
    """Formatuje bajty do KB/MB."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


class DraggableFileCard(QFrame):
    """
    Karta pliku na półce.
    Można ją złapać myszką i PRZECIĄGNĄĆ na zewnątrz (do Discorda, folderu, przeglądarki).
    """
    def __init__(self, file_path: str, on_remove_callback, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.on_remove_callback = on_remove_callback
        self.drag_start_pos = QPoint()

        self.setFrameShape(QFrame.Shape.StyledPanel)
        card_bg = theme_manager.card_bg
        card_border = theme_manager.card_border
        hover_bg = theme_manager.hover_bg
        text_pri = theme_manager.text_primary
        text_sec = theme_manager.text_secondary

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {card_bg};
                border-radius: 8px;
                border: 1px solid {card_border};
            }}
            QFrame:hover {{
                background-color: {hover_bg};
                border: 1px solid {card_border};
            }}
        """)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 6, 2)
        layout.setSpacing(8)

        # Rozszerzenie jako badge (np. PNG, PDF, ZIP)
        ext = os.path.splitext(file_path)[1].replace(".", "").upper()[:4]
        if not ext:
            ext = "PLIK"
        
        badge = QLabel(ext, self)
        badge.setStyleSheet(
            f"background-color: {card_border}; color: {text_pri}; font-weight: bold; "
            f"font-size: 8px; padding: 2px 4px; border-radius: 4px;"
        )
        badge.setFixedHeight(16)

        # Nazwa pliku
        name = os.path.basename(file_path)
        name_label = QLabel(name if len(name) <= 24 else name[:21] + "…", self)
        name_label.setStyleSheet(f"color: {text_pri}; font-size: 11px; font-weight: 500;")

        # Rozmiar
        size_str = ""
        try:
            size_str = format_file_size(os.path.getsize(file_path))
        except Exception:
            pass

        size_label = QLabel(size_str, self)
        size_label.setStyleSheet(f"color: {text_sec}; font-size: 10px;")

        # Autorski wektorowy przycisk usuwania (Zero emotek)
        from ui.vector_controls import VectorCloseButton
        btn_close = VectorCloseButton(size=18, parent=self)
        btn_close.clicked.connect(lambda: self.on_remove_callback(self.file_path))

        layout.addWidget(badge)
        layout.addWidget(name_label)
        layout.addWidget(size_label)
        layout.addStretch()
        layout.addWidget(btn_close)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Uruchamia natywny OLE Drag & Drop do innych aplikacji Windowsa."""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(self.file_path)])
        drag.setMimeData(mime)

        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag.exec(Qt.DropAction.CopyAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)


class DropShelfManager:
    """Globalny rejestr plików na półce."""
    def __init__(self):
        self.files = []
        self.listeners = []

    def add_file(self, path: str):
        if os.path.exists(path) and path not in self.files:
            self.files.append(path)
            self._notify()

    def remove_file(self, path: str):
        if path in self.files:
            self.files.remove(path)
            self._notify()

    def clear(self):
        if self.files:
            self.files.clear()
            self._notify()

    def count(self) -> int:
        return len(self.files)

    def subscribe(self, callback):
        self.listeners.append(callback)

    def _notify(self):
        for cb in self.listeners:
            try:
                cb(self.files)
            except Exception:
                pass


# Wspólna instancja menedżera półki
shelf_manager = DropShelfManager()
