"""
Wysokowydajny serwis multimediów (Windows SMTC).
Używa pojedynczego, stałego procesu w tle (Zero CPU spikes)
oraz natywnych wywołań User32 C-API dla natychmiastowej reakcji na kliknięcia.
"""
import ctypes
import json
import subprocess
import sys
import threading
import uuid
from PyQt6.QtCore import QThread, pyqtSignal

# Kody wirtualnych klawiszy multimedialnych Win32
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def send_media_key(vk_code: int):
    """Błyskawiczne wysłanie klawisza multimedialnego przez User32 C-API."""
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
    except Exception as err:
        print(f"[MediaKey Error] {err}")


def _send_smtc_command(action: str):
    """Control the current Windows media session without sending media keys."""
    operations = {
        "toggle": "$session.TryTogglePlayPauseAsync()",
        "next": "$session.TrySkipNextAsync()",
        "previous": "$session.TrySkipPreviousAsync()",
    }
    operation = operations.get(action)
    if not operation:
        return

    script = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
}[0]
function Await-WinRT($asyncOp, $type) {
    $method = $asTaskGeneric.MakeGenericMethod($type)
    $task = $method.Invoke($null, @($asyncOp))
    $task.Wait()
    return $task.Result
}
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime] | Out-Null
$managerOp = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()
$manager = Await-WinRT $managerOp ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$session = $manager.GetCurrentSession()
if (-not $session) {
    $sessions = $manager.GetSessions()
    if ($sessions.Count -gt 0) { $session = $sessions[0] }
}
if ($session) {
    $operation = __OPERATION__
    $null = Await-WinRT $operation ([System.Boolean])
}
'''.replace("__OPERATION__", operation)

    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as error:
        print(f"[SMTC Command Error] {error}")


def media_play_pause():
    _send_smtc_command("toggle")


def media_next():
    _send_smtc_command("next")


def media_prev():
    _send_smtc_command("previous")


def media_seek(position_seconds: float):
    """Seek in the active Windows media session to the requested position."""
    try:
        ticks = max(0, int(float(position_seconds) * 10_000_000))
    except (TypeError, ValueError, OverflowError):
        return
    script = r'''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
}[0]
function Await-WinRT($asyncOp, $type) {
    $method = $asTaskGeneric.MakeGenericMethod($type)
    $task = $method.Invoke($null, @($asyncOp))
    $task.Wait()
    return $task.Result
}
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime] | Out-Null
$manager = Await-WinRT ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$session = $manager.GetCurrentSession()
if (-not $session) { $sessions = $manager.GetSessions(); if ($sessions.Count -gt 0) { $session = $sessions[0] } }
if ($session) { $null = Await-WinRT ($session.TryChangePlaybackPositionAsync(__TICKS__)) ([System.Boolean]) }
'''.replace("__TICKS__", str(ticks))
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            startupinfo=startupinfo, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as error:
        print(f"[SMTC Seek Error] {error}")


class _GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]

    @classmethod
    def from_string(cls, value):
        return cls((ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


def _com_call(pointer, index, restype, *argtypes):
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    function = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])
    return function


def _with_default_audio_endpoint(action):
    """Run action against the default Windows render endpoint volume interface."""
    ole32 = ctypes.windll.ole32
    initialized = ole32.CoInitialize(None) in (0, 1)
    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()
    endpoint = ctypes.c_void_p()
    try:
        clsid = _GUID.from_string("BCDE0395-E52F-467C-8E3D-C4579291692E")
        iid_enumerator = _GUID.from_string("A95664D2-9614-4F35-A746-DE8DB63617E6")
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid_enumerator), ctypes.byref(enumerator))
        if hr < 0:
            return None
        hr = _com_call(enumerator, 4, ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(enumerator, 0, 1, ctypes.byref(device))
        if hr < 0:
            return None
        iid_volume = _GUID.from_string("5CDF2C82-841E-4546-9722-0CF74078229A")
        hr = _com_call(device, 3, ctypes.c_long, ctypes.POINTER(_GUID), ctypes.c_ulong, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(device, ctypes.byref(iid_volume), 23, None, ctypes.byref(endpoint))
        if hr < 0:
            return None
        return action(endpoint)
    except Exception:
        return None
    finally:
        for pointer in (endpoint, device, enumerator):
            if pointer and pointer.value:
                try:
                    _com_call(pointer, 2, ctypes.c_ulong)(pointer)
                except Exception:
                    pass
        if initialized:
            ole32.CoUninitialize()


def get_system_volume():
    def read(endpoint):
        value = ctypes.c_float()
        hr = _com_call(endpoint, 9, ctypes.c_long, ctypes.POINTER(ctypes.c_float))(endpoint, ctypes.byref(value))
        return round(max(0.0, min(1.0, value.value)) * 100) if hr >= 0 else None
    return _with_default_audio_endpoint(read)


def set_system_volume(percent: int):
    value = max(0.0, min(100.0, float(percent))) / 100.0
    def write(endpoint):
        hr = _com_call(endpoint, 7, ctypes.c_long, ctypes.c_float, ctypes.c_void_p)(endpoint, ctypes.c_float(value), None)
        return hr >= 0
    return bool(_with_default_audio_endpoint(write))


# Stały skrypt-demon PowerShell nasłuchujący sesji SMTC w jednej pętli (0% CPU)
POWERSHELL_DAEMON_SCRIPT = '''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { 
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
}[0]

function Await-WinRT($asyncOp, $type) {
    $method = $asTaskGeneric.MakeGenericMethod($type)
    $task = $method.Invoke($null, @($asyncOp))
    $task.Wait()
    return $task.Result
}

[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties,Windows.Media.Control,ContentType=WindowsRuntime] | Out-Null

$op = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()
$mgr = Await-WinRT $op ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])

$lastHash = ""
$lastPosition = -1.0

while ($true) {
    try {
        $session = $mgr.GetCurrentSession()
        if ($session) {
            $infoOp = $session.TryGetMediaPropertiesAsync()
            $info = Await-WinRT $infoOp ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
            $playback = $session.GetPlaybackInfo()
            
            $title = if ($info.Title) { $info.Title } else { "Nieznany utwór" }
            $artist = if ($info.Artist) { $info.Artist } else { "Nieznany wykonawca" }
            $status = if ($playback) { $playback.PlaybackStatus.ToString() } else { "Unknown" }
            $source = if ($session.SourceAppUserModelId) { $session.SourceAppUserModelId } else { "" }
            $timeline = $session.GetTimelineProperties()
            $position = if ($timeline) { [Math]::Max(0, $timeline.Position.TotalSeconds) } else { 0 }
            $duration = if ($timeline) { [Math]::Max(0, ($timeline.EndTime - $timeline.StartTime).TotalSeconds) } else { 0 }
            
            $currHash = "$title|$artist|$status|$source|$duration"
            if (($currHash -ne $lastHash) -or ([Math]::Abs($position - $lastPosition) -ge 0.8)) {
                $lastHash = $currHash
                $lastPosition = $position
                $obj = @{
                    has_media = $true
                    title = $title
                    artist = $artist
                    status = $status
                    source = $source
                    position_seconds = $position
                    duration_seconds = $duration
                }
                [Console]::WriteLine(($obj | ConvertTo-Json -Compress))
            }
        } else {
            if ($lastHash -ne "NONE") {
                $lastHash = "NONE"
                [Console]::WriteLine('{"has_media": false}')
            }
        }
    } catch {
        # Ciche pominięcie chwilowych błędów odczytu
    }
    Start-Sleep -Milliseconds 600
}
'''


# Isolated one-shot request: artwork I/O must never block the media status daemon.
POWERSHELL_ARTWORK_SCRIPT = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
}[0]
function Await-WinRT($asyncOp, $type) {
    $method = $asTaskGeneric.MakeGenericMethod($type)
    $task = $method.Invoke($null, @($asyncOp))
    $task.Wait()
    return $task.Result
}
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties,Windows.Media.Control,ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStreamWithContentType,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataReader,Windows.Storage,ContentType=WindowsRuntime] | Out-Null

$manager = Await-WinRT ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$session = $manager.GetCurrentSession()
if (-not $session) {
    $sessions = @($manager.GetSessions())
    if ($sessions.Count -gt 0) { $session = $sessions[0] }
}
$matchedInfo = if ($session) {
    Await-WinRT ($session.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
} else { $null }

$thumbnailBase64 = ''
if ($matchedInfo -and $matchedInfo.Thumbnail) {
    $stream = $null
    $reader = $null
    try {
        $stream = Await-WinRT ($matchedInfo.Thumbnail.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
        if ($stream) {
            $reader = [Windows.Storage.Streams.DataReader]::new($stream.GetInputStreamAt(0))
            $loaded = Await-WinRT ($reader.LoadAsync([UInt32]4194304)) ([UInt32])
            if ($loaded -gt 0) {
                $bytes = New-Object byte[] ([int]$loaded)
                $reader.ReadBytes($bytes)
                $thumbnailBase64 = [Convert]::ToBase64String($bytes)
            }
        }
    } catch {
        $thumbnailBase64 = ''
    } finally {
        if ($reader) { $reader.Dispose() }
        # WinRT stream is exposed as a COM object without a PowerShell Dispose method;
        # the short-lived helper process releases it on exit.
    }
}
[Console]::WriteLine($thumbnailBase64)
'''


class MediaMonitorWorker(QThread):
    """Działa w tle bez obciążania UI; odbiera zdarzenia ze stałego procesu."""
    media_updated = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.running = True
        self._process_lock = threading.Lock()

    def run(self):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # Ukryte okno PowerShell

        try:
            process = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_DAEMON_SCRIPT],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                startupinfo=startupinfo,
                bufsize=1
            )

            with self._process_lock:
                self.process = process
                should_run = self.running
            if not should_run:
                self._terminate_process(process)
                return

            while self.running and process.poll() is None:
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            data = json.loads(line)
                            self.media_updated.emit(data)
                        except Exception:
                            pass
        except Exception as e:
            print(f"[MediaWorker Error] {e}")
        finally:
            with self._process_lock:
                self.process = None

    @staticmethod
    def _terminate_process(process):
        if not process or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        except Exception:
            pass

    def stop(self):
        self.running = False
        with self._process_lock:
            process = self.process
        self._terminate_process(process)
        self.wait(3000)
