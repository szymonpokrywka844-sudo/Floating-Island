"""
Główny punkt startowy aplikacji Floating Island.
Automatycznie usuwa poprzednio uruchomione wersje przy starcie
oraz przeładowuje aplikację (Hot-Reload) w przypadku modyfikacji kodu.
"""
import os
import sys
import tempfile
import traceback

# Zapisuj ewentualne nieobsłużone wyjątki do pliku error.log
def _handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    log_root = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "FloatingIsland")
    try:
        os.makedirs(log_root, exist_ok=True)
        log_path = os.path.join(log_root, "error.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("=" * 50 + "\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    except OSError:
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = _handle_unhandled_exception

from PyQt6.QtWidgets import QApplication

from core.reloader import (
    kill_previous_instances, register_current_instance,
    cleanup_stale_pycache, CodeChangeReloader,
)
from ui.island_window import FloatingIsland
from ui.tray_manager import IslandTrayManager
from modules.media import MediaModule
from core.updater import AutoUpdateManager


def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))

    # Przy hot-reloadzie poprzednia instancja wyjdzie łagodnie po sprzątnięciu wątków.
    is_replacement = os.environ.pop("FLOATING_ISLAND_REPLACEMENT", "") == "1"
    if is_replacement:
        register_current_instance()
    else:
        kill_previous_instances()
    cleanup_stale_pycache(root_dir)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Automatyczne aktualizacje z gałęzi GitHub `main`.
    updater = AutoUpdateManager(parent=app)
    app._floating_island_updater = updater

    # 2. Watcher kodu: automatyczny restart i usunięcie starej wersji po edycji plików .py
    reloader = CodeChangeReloader(root_dir)

    # 3. Tworzymy powłokę wyspy
    island = FloatingIsland()

    # 4. Inicjalizujemy uniwersalny moduł multimediów, półki i skrótów
    media_module = MediaModule()
    island.set_module(media_module)

    # 5. Inicjalizujemy ikonę w zasobniku systemowym (Tray) z autostartem
    tray = IslandTrayManager(island)

    # Zachowaj referencje do komponentów przez cały czas działania Qt.
    app._floating_island_components = (updater, reloader, island, media_module, tray)

    # 6. Wyświetlamy wyspę na ekranie
    island.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
