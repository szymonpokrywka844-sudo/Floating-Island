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
            
            $currHash = "$title|$artist|$status|$source"
            if ($currHash -ne $lastHash) {
                $lastHash = $currHash
                $obj = @{
                    has_media = $true
                    title = $title
                    artist = $artist
                    status = $status
                    source = $source
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
