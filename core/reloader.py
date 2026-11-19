"""
Mechanizm usuwania starych instancji procesu oraz automatycznego
przeładowywania aplikacji (Auto-Reload / Hot-Reload) po zmianach w kodzie.
Wydajny, natywny Win32 TerminateProcess + stabilny polling mtime.
"""
import os
import sys
import subprocess
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication

PID_FILE = os.path.join(os.environ.get("TEMP", "C:/Windows/Temp"), "floating_island.pid")


def kill_previous_instances():
    """
    Zamyka poprzednią instancję tylko wtedy, gdy PID nadal należy do tego projektu.
    To zabezpiecza przed zabiciem obcego procesu po ponownym użyciu numeru PID.
    """
    current_pid = os.getpid()

    if os.path.isfile(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                old_pid = int(f.read().strip())
            if old_pid != current_pid and old_pid > 0:
                _terminate_if_this_app(old_pid)
        except Exception:
            pass

    _write_current_pid(current_pid)


def _write_current_pid(pid: int):
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except Exception:
        pass


def register_current_instance():
    """Rejestruje proces, który zastępuje poprzednią instancję przy hot-reloadzie."""
    _write_current_pid(os.getpid())


def _terminate_if_this_app(pid: int):
    main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
    escaped_main = main_py.replace("'", "''")
    command = (
        f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; "
        f"$expected = '{escaped_main}'; "
        "if ($p -and ($p.Name -eq 'python.exe' -or $p.Name -eq 'pythonw.exe') "
        "-and $p.CommandLine -and $p.CommandLine.IndexOf($expected, "
        "[System.StringComparison]::OrdinalIgnoreCase) -ge 0) { "
        f"Get-CimInstance Win32_Process -Filter 'ParentProcessId = {pid}' | "
        "Where-Object { $_.Name -eq 'powershell.exe' -and $_.CommandLine -match "
        "'GlobalSystemMediaTransportControlsSessionManager|UserNotificationListener' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; "
        "Start-Sleep -Milliseconds 100; "
        f"Stop-Process -Id {pid} -Force }}"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except Exception:
        return False


def cleanup_stale_pycache(root_dir: str):
    """Usuwa stare skompilowane pliki .pyc, aby wymusić ładowanie świeżego kodu źródłowego."""
    try:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            if "__pycache__" in dirnames:
                cache_path = os.path.join(dirpath, "__pycache__")
                try:
                    for f in os.listdir(cache_path):
                        if f.endswith(".pyc"):
                            os.remove(os.path.join(cache_path, f))
                except Exception:
                    pass
    except Exception:
        pass


class CodeChangeReloader(QObject):
    """
    Watcher monitorujący zmiany w plikach źródłowych .py aplikacji.
    Sprawdza czasy modyfikacji (mtime) plików .py raz na 1200ms.
    Gdy wykryje faktyczną modyfikację i zapis pliku źródłowego,
    uruchamia zaktualizowany proces i natychmiast zamyka starą wersję.
    """
    def __init__(self, root_dir: str, parent=None):
        super().__init__(parent)
        self.root_dir = os.path.abspath(root_dir)
        self.subdirs = ["", "core", "modules", "ui"]
        self.file_mtimes = {}

        # Zainicjuj czasy modyfikacji istniejących plików .py
        self._scan_files(initial=True)

        # Sprawdzanie co 1200ms
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_for_changes)
        self.timer.start(1200)

    def pause(self):
        """Stop watching while the updater replaces source files."""
        self.timer.stop()

    def resume(self):
        """Refresh timestamps before watching again after a failed update."""
        self._scan_files(initial=True)
        if not self.timer.isActive():
            self.timer.start(1200)

    def _get_all_py_files(self):
        py_files = []
        for sub in self.subdirs:
            full_path = os.path.join(self.root_dir, sub) if sub else self.root_dir
            if os.path.isdir(full_path):
                try:
                    for fname in os.listdir(full_path):
                        if fname.endswith(".py") and not fname.startswith("test_") and not fname.startswith("."):
                            py_files.append(os.path.join(full_path, fname))
                except Exception:
                    pass
        return py_files

    def _scan_files(self, initial=False):
        for fpath in self._get_all_py_files():
            try:
                mtime = os.path.getmtime(fpath)
                if initial or fpath not in self.file_mtimes:
                    self.file_mtimes[fpath] = mtime
            except OSError:
                pass

    def _check_for_changes(self):
        current_files = self._get_all_py_files()
        changed_file = None

        for fpath in current_files:
            try:
                mtime = os.path.getmtime(fpath)
                if fpath not in self.file_mtimes:
                    self.file_mtimes[fpath] = mtime
                    changed_file = fpath
                    break
                elif mtime > self.file_mtimes[fpath] + 0.1:
                    changed_file = fpath
                    break
            except OSError:
                continue

        if changed_file:
            self._restart_app(changed_file)

    def _restart_app(self, changed_file: str):
        main_py = os.path.join(self.root_dir, "main.py")
        if not os.path.isfile(main_py):
            return

        print(f"[Floating Island] Zmiana w {os.path.basename(changed_file)}. Przeładowywanie...")

        python_exe = sys.executable
        pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
        exe_to_use = pythonw_exe if os.path.isfile(pythonw_exe) else python_exe

        # Wyczyść stary bytecode
        cleanup_stale_pycache(self.root_dir)

        try:
            child_env = os.environ.copy()
            child_env["FLOATING_ISLAND_REPLACEMENT"] = "1"
            subprocess.Popen(
                [exe_to_use, main_py],
                cwd=self.root_dir,
                env=child_env,
            )
        except Exception as e:
            print(f"[Floating Island] Błąd restartu: {e}")
            return

        # Zamknięcie przez event loop uruchamia procedury sprzątające wątki i subprocessy.
        app = QApplication.instance()
        if app:
            app.quit()
        else:
            os._exit(0)
