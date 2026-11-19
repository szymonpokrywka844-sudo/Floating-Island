"""Automatic source updates from the configured GitHub branch."""
import io
import json
import os
import stat
import subprocess
import sys
import urllib.request
import zipfile

from PyQt6.QtCore import QObject, QSettings, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

DEFAULT_REPO = "szymonpokrywka844-sudo/Floating-Island"
DEFAULT_BRANCH = "main"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def project_directory():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _safe_update_destination(project_dir, root_prefix, member_name):
    if not member_name.startswith(root_prefix):
        raise ValueError("Archiwum zawiera wpis poza katalogiem projektu.")
    relative_name = member_name[len(root_prefix):].rstrip("/")
    parts = relative_name.split("/")
    if not relative_name or any(p in ("", ".", "..") for p in parts) or any(
        "\\" in p or ":" in p or "\x00" in p for p in parts
    ):
        raise ValueError("Archiwum zawiera niebezpieczną ścieżkę.")
    root = os.path.realpath(project_dir)
    destination = os.path.realpath(os.path.join(root, *parts))
    if os.path.commonpath((root, destination)) != root:
        raise ValueError("Ścieżka aktualizacji wychodzi poza katalog aplikacji.")
    return destination


def get_current_commit():
    root = project_directory()
    try:
        with open(os.path.join(root, "version.json"), encoding="utf-8") as f:
            recorded = json.load(f).get("commit")
            if recorded:
                return recorded
    except (OSError, ValueError, TypeError):
        pass
    if os.path.isdir(os.path.join(root, ".git")):
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root,
                stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW,
                timeout=5,
            ).decode().strip()
        except Exception:
            pass
    return "initial"


def save_current_commit(commit_sha, repo=DEFAULT_REPO, branch=DEFAULT_BRANCH):
    """Persist the installed baseline so a missing marker does not retrigger forever."""
    path = os.path.join(project_directory(), "version.json")
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as version_file:
        json.dump({"commit": commit_sha, "repo": repo, "branch": branch}, version_file, indent=2)
    os.replace(temporary, path)


class UpdateWorker(QThread):
    check_finished = pyqtSignal(bool, dict)

    def __init__(self, repo, branch, parent=None):
        super().__init__(parent)
        self.repo, self.branch = repo, branch

    def run(self):
        url = f"https://api.github.com/repos/{self.repo}/commits/{self.branch}"
        request = urllib.request.Request(url, headers={
            "User-Agent": "FloatingIsland-Updater",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            sha = data.get("sha", "")
            info = {
                "sha": sha, "short_sha": sha[:7],
                "message": data.get("commit", {}).get("message", "").split("\n")[0],
                "author": data.get("commit", {}).get("author", {}).get("name", ""),
            }
            local = get_current_commit()
            if local == "initial" and sha:
                save_current_commit(sha, self.repo, self.branch)
                self.check_finished.emit(False, info)
            else:
                self.check_finished.emit(bool(sha and sha != local), info)
        except Exception as error:
            self.check_finished.emit(False, {"error": str(error)})


class ApplyUpdateWorker(QThread):
    finished_update = pyqtSignal(bool, str)

    def __init__(self, repo, branch, commit_info, parent=None):
        super().__init__(parent)
        self.repo, self.branch, self.commit_info = repo, branch, commit_info

    def run(self):
        try:
            root = project_directory()
            url = f"https://api.github.com/repos/{self.repo}/zipball/{self.branch}"
            request = urllib.request.Request(url, headers={
                "User-Agent": "FloatingIsland-Updater",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            })
            with urllib.request.urlopen(request, timeout=60) as response:
                archive = response.read()
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                files = [item for item in bundle.infolist() if not item.is_dir()]
                if not files:
                    raise ValueError("Pobrane archiwum jest puste.")
                first = files[0].filename.split("/", 1)[0]
                if not first or first in (".", "..") or "\\" in first or ":" in first:
                    raise ValueError("Archiwum ma nieprawidłowy katalog główny.")
                prefix = first + "/"
                validated = []
                for item in files:
                    if not item.filename.startswith(prefix):
                        raise ValueError("Archiwum zawiera wpis poza katalogiem projektu.")
                    rel = item.filename[len(prefix):]
                    if not rel or any(p.startswith(".") for p in rel.split("/")):
                        continue
                    if stat.S_ISLNK(item.external_attr >> 16):
                        raise ValueError("Archiwum zawiera dowiązany plik.")
                    validated.append((item, _safe_update_destination(root, prefix, item.filename)))
                for item, destination in validated:
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    with bundle.open(item) as source, open(destination, "wb") as target:
                        target.write(source.read())
            sha = self.commit_info.get("sha")
            if sha:
                with open(os.path.join(root, "version.json"), "w", encoding="utf-8") as f:
                    json.dump({"commit": sha, "repo": self.repo, "branch": self.branch}, f, indent=2)
            self.finished_update.emit(True, "Aktualizacja zainstalowana. Uruchamiam ponownie aplikację.")
        except Exception as error:
            self.finished_update.emit(False, f"Aktualizacja nie powiodła się: {error}")


class AutoUpdateManager(QObject):
    update_available = pyqtSignal(dict)
    check_started = pyqtSignal()
    update_status = pyqtSignal(str)
    update_completed = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        settings = QSettings("FloatingIsland", "FloatingIsland")
        self.repo = str(settings.value("update_repo", DEFAULT_REPO))
        self.branch = str(settings.value("update_branch", DEFAULT_BRANCH))
        self.pending_commit_info = None
        self._checking = False
        self._applying = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_for_updates)
        self.timer.start(15 * 60 * 1000)
        QTimer.singleShot(8000, self.check_for_updates)

    def check_for_updates(self):
        if self._checking or self._applying:
            return
        self._checking = True
        self.check_started.emit()
        self.worker = UpdateWorker(self.repo, self.branch, self)
        self.worker.check_finished.connect(self._on_check_finished)
        self.worker.start()

    def _on_check_finished(self, has_update, info):
        self._checking = False
        if has_update:
            self.pending_commit_info = info
            self.update_available.emit(info)
            self.apply_update()
        else:
            self.update_status.emit(info.get("error", "Aplikacja jest aktualna."))

    def apply_update(self):
        if self._applying or not self.pending_commit_info:
            return
        self._applying = True
        self.update_status.emit("Pobieranie aktualizacji z GitHub…")
        self.apply_worker = ApplyUpdateWorker(
            self.repo, self.branch, self.pending_commit_info, self
        )
        self.apply_worker.finished_update.connect(self._on_update_finished)
        self.apply_worker.start()

    def _on_update_finished(self, success, message):
        self._applying = False
        self.update_completed.emit(success, message)
        self.update_status.emit(message)
        if success:
            self._restart_app()

    def _restart_app(self):
        root = project_directory()
        vbs = os.path.join(root, "Uruchom_w_tle.vbs")
        env = os.environ.copy()
        env["FLOATING_ISLAND_REPLACEMENT"] = "1"
        if os.path.isfile(vbs):
            subprocess.Popen(["wscript.exe", vbs], cwd=root, env=env)
        elif getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable], cwd=root, env=env)
        else:
            subprocess.Popen([sys.executable, os.path.join(root, "main.py")], cwd=root, env=env)
        app = QApplication.instance()
        if app:
            app.quit()

