"""
Menedżer ikony w zasobniku systemowym (Windows System Tray)
oraz menu kontekstowego (PPM) z opcją autostartu i kontroli wyspy.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from core.autostart import is_autostart_enabled, set_autostart
from modules.dropshelf import shelf_manager


def create_tray_icon() -> QIcon:
    """Tworzy wektorową, minimalistyczną ikonę pigułki dla zasobnika Windows."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Czarna pigułka z białą obwódką
    painter.setBrush(QColor(18, 18, 20))
    painter.setPen(QColor(255, 255, 255, 220))
    painter.drawRoundedRect(3, 10, 26, 12, 6, 6)

    # Biała mała kropka w środku
    painter.setBrush(QColor(255, 255, 255))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(13, 13, 6, 6)

    painter.end()
    return QIcon(pixmap)


def create_context_menu(island_widget) -> QMenu:
    """Tworzy nowoczesne, ciemne menu kontekstowe dla wyspy i ikony w trayu."""
    menu = QMenu()
    menu.setStyleSheet("""
        QMenu {
            background-color: #1A1A1E;
            color: #FFFFFF;
            border: 1px solid #303036;
            border-radius: 8px;
            padding: 4px;
            font-size: 11px;
            font-weight: 500;
        }
        QMenu::item {
            padding: 6px 20px 6px 12px;
            border-radius: 4px;
        }
        QMenu::item:selected {
            background-color: #2C2C34;
        }
        QMenu::item:disabled {
            color: #636366;
            font-weight: bold;
        }
        QMenu::separator {
            height: 1px;
            background-color: #2A2A30;
            margin: 4px 6px;
        }
    """)

    # Nagłówek
    header = QAction("Floating Island", menu)
    header.setEnabled(False)
    menu.addAction(header)
    menu.addSeparator()

    # Opcja autostartu z Windowsem (Checkable)
    autostart_action = QAction("Uruchamiaj ze startem systemu", menu)
    autostart_action.setCheckable(True)
    autostart_action.setChecked(is_autostart_enabled())

    def toggle_autostart():
        new_state = autostart_action.isChecked()
        set_autostart(new_state)

    autostart_action.triggered.connect(toggle_autostart)
    menu.addAction(autostart_action)

    # Opróżnienie półki
    clear_shelf_action = QAction("Wyczyść półkę na pliki", menu)
    clear_shelf_action.triggered.connect(shelf_manager.clear)
    menu.addAction(clear_shelf_action)

    menu.addSeparator()

    # Wyśrodkowanie pozycji
    recenter_action = QAction("Wyśrodkuj na ekranie", menu)
    recenter_action.triggered.connect(island_widget.recenter)
    menu.addAction(recenter_action)

    menu.addSeparator()

    # Zamknięcie programu
    exit_action = QAction("Zakończ", menu)
    exit_action.triggered.connect(QApplication.quit)
    menu.addAction(exit_action)

    return menu


class IslandTrayManager:
    """Zarządza obecnością aplikacji w pasku zadań obok zegarka."""
    def __init__(self, island_widget):
        self.island = island_widget
        self.tray = QSystemTrayIcon(create_tray_icon(), island_widget)
        self.tray.setToolTip("Floating Island • Windows")

        # Przypisanie menu kontekstowego
        self.menu = create_context_menu(island_widget)
        self.tray.setContextMenu(self.menu)

        # Kliknięcie lewym klawiszem w trayu -> rozwiń / zwiń wyspę
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.island.is_expanded:
                self.island.collapse()
            else:
                self.island.expand()
