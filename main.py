"""
Główny punkt startowy aplikacji Floating Island.
Automatycznie usuwa poprzednio uruchomione wersje przy starcie
oraz przeładowuje aplikację (Hot-Reload) w przypadku modyfikacji kodu.
"""
import os
import sys
import tempfile
import traceback

MAX_ERROR_LOG_BYTES = 1024 * 1024
MAX_ERROR_ENTRY_BYTES = 256 * 1024

# Zapisuj ewentualne nieobsłużone wyjątki do pliku error.log
def _handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    log_root = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "FloatingIsland")
    try:
        os.makedirs(log_root, exist_ok=True)
        log_path = os.path.join(log_root, "error.log")
        backup_path = log_path + ".1"
        entry = "=" * 50 + "\n" + "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
        entry_bytes = entry.encode("utf-8", errors="replace")
        if len(entry_bytes) > MAX_ERROR_ENTRY_BYTES:
            entry_bytes = entry_bytes[-MAX_ERROR_ENTRY_BYTES:]
        current_size = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        if current_size + len(entry_bytes) > MAX_ERROR_LOG_BYTES:
            try:
                os.remove(backup_path)
            except FileNotFoundError:
                pass
            if os.path.exists(log_path):
                os.replace(log_path, backup_path)
        with open(log_path, "ab") as f:
            f.write(entry_bytes)
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
from core.app_icon import create_app_icon


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
    app_icon = create_app_icon()
    app.setWindowIcon(app_icon)

    # Automatyczne aktualizacje z gałęzi GitHub `main`.
    updater = AutoUpdateManager(parent=app)
    app._floating_island_updater = updater

    # Watcher kodu jest potrzebny tylko w checkoutcie developerskim.
    # Instalator nie zawiera .git, a updater sam restartuje aplikację po podmianie plików.
    reloader = (
        CodeChangeReloader(root_dir)
        if os.path.isdir(os.path.join(root_dir, ".git"))
        else None
    )
    if reloader:
        updater.update_started.connect(reloader.pause)

        def resume_reloader_after_failed_update(success, _message):
            if not success:
                reloader.resume()

        updater.update_completed.connect(resume_reloader_after_failed_update)

    # 3. Tworzymy powłokę wyspy
    island = FloatingIsland()
    island.setWindowIcon(app_icon)

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
