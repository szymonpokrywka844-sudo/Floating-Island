"""Store small secrets protected for the current Windows user with DPAPI."""
import ctypes
from ctypes import wintypes

from PyQt6.QtCore import QSettings

TOKEN_KEY = "github_update_token_dpapi"
CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _free_blob(pointer):
    local_free = ctypes.windll.kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p
    local_free(ctypes.cast(pointer, ctypes.c_void_p))


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _protect(data: bytes) -> bytes:
    if not hasattr(ctypes, "windll"):
        raise OSError("Szyfrowanie tokena wymaga systemu Windows.")
    source, source_buffer = _blob(data)
    result = _DataBlob()
    protect = ctypes.windll.crypt32.CryptProtectData
    protect.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
        wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    protect.restype = wintypes.BOOL
    ok = protect(
        ctypes.byref(source), "Floating Island GitHub updater", None,
        None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        _free_blob(result.pbData)


def _unprotect(data: bytes) -> bytes:
    if not hasattr(ctypes, "windll"):
        raise OSError("Odszyfrowanie tokena wymaga systemu Windows.")
    source, source_buffer = _blob(data)
    result = _DataBlob()
    description = wintypes.LPWSTR()
    unprotect = ctypes.windll.crypt32.CryptUnprotectData
    unprotect.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob), wintypes.LPVOID, wintypes.LPVOID,
        wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    unprotect.restype = wintypes.BOOL
    ok = unprotect(
        ctypes.byref(source), ctypes.byref(description), None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        _free_blob(result.pbData)


def save_github_token(token: str, settings=None):
    settings = settings or QSettings("FloatingIsland", "FloatingIsland")
    token = token.strip()
    if not token:
        settings.remove(TOKEN_KEY)
        settings.sync()
        return
    protected = _protect(token.encode("utf-8"))
    settings.setValue(TOKEN_KEY, protected.hex())
    settings.sync()


def load_github_token(settings=None) -> str:
    settings = settings or QSettings("FloatingIsland", "FloatingIsland")
    encoded = settings.value(TOKEN_KEY, "")
    if not encoded:
        return ""
    try:
        return _unprotect(bytes.fromhex(str(encoded))).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""
