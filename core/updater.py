"""Automatic source updates from the configured GitHub branch."""
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import quote
import zipfile

from PyQt6.QtCore import QObject, QSettings, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

DEFAULT_REPO = "szymonpokrywka844-sudo/Floating-Island"
DEFAULT_BRANCH = "main"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_API_RESPONSE_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 4096
MAX_UPDATE_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_UPDATE_BYTES = 128 * 1024 * 1024

_REPO_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_BRANCH_RE = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\Z")
_SHA_RE = re.compile(r"[0-9a-fA-F]{40}\Z")


def _validated_source(repo, branch):
    repo = str(repo or "")
    branch = str(branch or "")
    if not _REPO_RE.fullmatch(repo) or ".." in repo:
        raise ValueError("Nieprawidłowy adres repozytorium aktualizacji.")
    if (
        not _BRANCH_RE.fullmatch(branch)
        or any(part in (".", "..") or part.lower().endswith(".lock") for part in branch.split("/"))
        or ".." in branch
    ):
        raise ValueError("Nieprawidłowa nazwa gałęzi aktualizacji.")
    return repo, branch


def _read_limited(response, limit):
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_size = int(content_length)
        except (TypeError, ValueError) as error:
            raise ValueError("Serwer zwrócił nieprawidłowy rozmiar odpowiedzi.") from error
        if declared_size > limit:
            raise ValueError("Odpowiedź serwera przekracza dozwolony rozmiar.")

    chunks = []
    total = 0
    while True:
        chunk = response.read(min(64 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError("Odpowiedź serwera przekracza dozwolony rozmiar.")
        chunks.append(chunk)
    return b"".join(chunks)


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
    cursor = root
    for part in parts:
        cursor = os.path.join(cursor, part)
        if os.path.islink(cursor):
            raise ValueError("Aktualizacja nie może zapisywać przez dowiązanie symboliczne.")
    destination = os.path.realpath(os.path.join(root, *parts))
    if os.path.commonpath((root, destination)) != root:
        raise ValueError("Ścieżka aktualizacji wychodzi poza katalog aplikacji.")
    return destination


def _stage_and_apply_update(archive_bytes, root, repo, branch, commit_sha):
    if not _SHA_RE.fullmatch(str(commit_sha or "")):
        raise ValueError("Brak poprawnego identyfikatora commita aktualizacji.")

    root = os.path.realpath(root)
    staging = tempfile.mkdtemp(prefix=".floating-island-update-", dir=root)
    applied = []
    preserve_staging = False
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as bundle:
            infos = bundle.infolist()
            if not infos or len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("Archiwum ma nieprawidłową liczbę plików.")
            files = [item for item in infos if not item.is_dir()]
            if not files:
                raise ValueError("Pobrane archiwum jest puste.")
            first = files[0].filename.split("/", 1)[0]
            if not first or first in (".", "..") or "\\" in first or ":" in first or "\x00" in first:
                raise ValueError("Archiwum ma nieprawidłowy katalog główny.")
            prefix = first + "/"
            validated = []
            seen_paths = set()
            total_declared_size = 0

            for item in files:
                if not item.filename.startswith(prefix):
                    raise ValueError("Archiwum zawiera wpis poza katalogiem projektu.")
                relative_name = item.filename[len(prefix):]
                parts = relative_name.split("/")
                if not relative_name or any(part.startswith(".") for part in parts):
                    continue
                destination = _safe_update_destination(root, prefix, item.filename)
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError("Archiwum zawiera dowiązany plik.")
                if item.flag_bits & 0x1:
                    raise ValueError("Archiwum zawiera zaszyfrowany wpis.")
                if item.file_size < 0 or item.file_size > MAX_UPDATE_FILE_BYTES:
                    raise ValueError("Plik aktualizacji przekracza dozwolony rozmiar.")
                total_declared_size += item.file_size
                if total_declared_size > MAX_TOTAL_UPDATE_BYTES:
                    raise ValueError("Archiwum przekracza łączny limit rozpakowania.")

                normalized = os.path.normcase(os.path.relpath(destination, root)).casefold()
                if normalized in seen_paths:
                    raise ValueError("Archiwum zawiera powtórzoną ścieżkę.")
                seen_paths.add(normalized)
                # The installed commit marker is generated locally after extraction.
                if normalized == os.path.normcase("version.json").casefold():
                    continue
                validated.append((item, relative_name, destination))

            for relative_name in (name for _item, name, _destination in validated):
                parts = relative_name.split("/")
                for index in range(1, len(parts)):
                    parent = os.path.normcase(os.path.join(*parts[:index])).casefold()
                    if parent in seen_paths:
                        raise ValueError("Archiwum ma konflikt nazw plików i katalogów.")

            new_root = os.path.join(staging, "new")
            os.makedirs(new_root, exist_ok=True)
            total_written = 0
            pending = []
            for item, relative_name, destination in validated:
                staged_path = os.path.join(new_root, *relative_name.split("/"))
                os.makedirs(os.path.dirname(staged_path), exist_ok=True)
                written = 0
                with bundle.open(item, "r") as source, open(staged_path, "wb") as target:
                    while True:
                        chunk = source.read(64 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        total_written += len(chunk)
                        if written > MAX_UPDATE_FILE_BYTES or total_written > MAX_TOTAL_UPDATE_BYTES:
                            raise ValueError("Rozpakowane archiwum przekracza dozwolony rozmiar.")
                        target.write(chunk)
                if written != item.file_size:
                    raise ValueError("Rozmiar pliku w archiwum jest niezgodny z jego zawartością.")
                pending.append((staged_path, destination, relative_name))

            version_stage = os.path.join(new_root, "version.json")
            with open(version_stage, "w", encoding="utf-8") as version_file:
                json.dump({"commit": commit_sha, "repo": repo, "branch": branch}, version_file, indent=2)
                version_file.flush()
                os.fsync(version_file.fileno())
            pending.append((version_stage, os.path.join(root, "version.json"), "version.json"))

        backup_root = os.path.join(staging, "backup")
        for staged_path, destination, relative_name in pending:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if os.path.isdir(destination) and not os.path.islink(destination):
                raise ValueError("Ścieżka aktualizacji wskazuje na katalog zamiast pliku.")
            backup_path = None
            if os.path.lexists(destination):
                backup_path = os.path.join(backup_root, *relative_name.split("/"))
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                os.replace(destination, backup_path)
            applied.append((destination, backup_path))
            os.replace(staged_path, destination)
    except Exception as error:
        rollback_errors = []
        for destination, backup_path in reversed(applied):
            try:
                if os.path.lexists(destination):
                    os.remove(destination)
                if backup_path and os.path.lexists(backup_path):
                    os.replace(backup_path, destination)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            preserve_staging = True
            raise RuntimeError(
                f"Aktualizacja nie powiodła się, a przywrócenie części plików też zawiodło: "
                f"{rollback_errors[0]}. Kopia zapasowa jest w {staging}."
            ) from error
        raise
    finally:
        if not preserve_staging:
            shutil.rmtree(staging, ignore_errors=True)


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
    try:
        with open(temporary, "w", encoding="utf-8") as version_file:
            json.dump({"commit": commit_sha, "repo": repo, "branch": branch}, version_file, indent=2)
            version_file.flush()
            os.fsync(version_file.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass


class UpdateWorker(QThread):
    check_finished = pyqtSignal(bool, dict)

    def __init__(self, repo, branch, parent=None):
        super().__init__(parent)
        self.repo, self.branch = repo, branch

    def run(self):
        try:
            repo, branch = _validated_source(self.repo, self.branch)
            url = (
                f"https://api.github.com/repos/{quote(repo, safe='/._-')}"
                f"/commits/{quote(branch, safe='/._-')}"
            )
            request = urllib.request.Request(url, headers={
                "User-Agent": "FloatingIsland-Updater",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            })
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(_read_limited(response, MAX_API_RESPONSE_BYTES).decode("utf-8"))
            sha = data.get("sha", "")
            if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
                raise ValueError("GitHub zwrócił nieprawidłowy identyfikator commita.")
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
            repo, branch = _validated_source(self.repo, self.branch)
            sha = str(self.commit_info.get("sha", ""))
            if not _SHA_RE.fullmatch(sha):
                raise ValueError("Brak poprawnego identyfikatora commita aktualizacji.")
            url = f"https://api.github.com/repos/{quote(repo, safe='/._-')}/zipball/{sha}"
            request = urllib.request.Request(url, headers={
                "User-Agent": "FloatingIsland-Updater",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            })
            with urllib.request.urlopen(request, timeout=60) as response:
                archive = _read_limited(response, MAX_ARCHIVE_BYTES)
            _stage_and_apply_update(archive, root, repo, branch, sha)
            self.finished_update.emit(True, "Aktualizacja zainstalowana. Uruchamiam ponownie aplikację.")
        except Exception as error:
            self.finished_update.emit(False, f"Aktualizacja nie powiodła się: {error}")


class AutoUpdateManager(QObject):
    update_available = pyqtSignal(dict)
    check_started = pyqtSignal()
    update_started = pyqtSignal()
    update_status = pyqtSignal(str)
    update_completed = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        settings = QSettings("FloatingIsland", "FloatingIsland")
        try:
            self.repo, self.branch = _validated_source(
                settings.value("update_repo", DEFAULT_REPO),
                settings.value("update_branch", DEFAULT_BRANCH),
            )
        except ValueError:
            self.repo, self.branch = DEFAULT_REPO, DEFAULT_BRANCH
        self.development_mode = (
            not getattr(sys, "frozen", False)
            and os.path.exists(os.path.join(project_directory(), ".git"))
        )
        self.enabled = not self.development_mode
        self.pending_commit_info = None
        self._checking = False
        self._applying = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_for_updates)
        if self.enabled:
            self.timer.start(15 * 60 * 1000)
            QTimer.singleShot(8000, self.check_for_updates)

    def check_for_updates(self):
        if not self.enabled:
            self.update_status.emit(
                "Aktualizacje wyłączone w lokalnej kopii developerskiej."
            )
            return
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
        self.update_started.emit()
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

