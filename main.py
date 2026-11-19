"""
Główny punkt startowy aplikacji Floating Island.
Automatycznie usuwa poprzednio uruchomione wersje przy starcie
oraz przeładowuje aplikację (Hot-Reload) w przypadku modyfikacji kodu.
"""
import os
import sys
import traceback

# Zapisuj ewentualne nieobsłużone wyjątki do pliku error.log
def _handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("=" * 50 + "\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = _handle_unhandled_exception

from PyQt6.QtWidgets import QApplication

from core.reloader import kill_previous_instances, cleanup_stale_pycache, CodeChangeReloader
from ui.island_window import FloatingIsland
from ui.tray_manager import IslandTrayManager
from modules.media import MediaModule


def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Bezwzględne usunięcie starych instancji procesu po zmianach w kodzie
    kill_previous_instances()
    cleanup_stale_pycache(root_dir)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 2. Watcher kodu: automatyczny restart i usunięcie starej wersji po edycji plików .py
    reloader = CodeChangeReloader(root_dir)

    # 3. Tworzymy powłokę wyspy
    island = FloatingIsland()

    # 4. Inicjalizujemy uniwersalny moduł multimediów, półki i skrótów
    media_module = MediaModule()
    island.set_module(media_module)

    # 5. Inicjalizujemy ikonę w zasobniku systemowym (Tray) z autostartem
    tray = IslandTrayManager(island)

    # 6. Wyświetlamy wyspę na ekranie
    island.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
