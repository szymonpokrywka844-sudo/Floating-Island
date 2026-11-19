"""
Wysokowydajny serwis multimediów (Windows SMTC).
Używa pojedynczego, stałego procesu w tle (Zero CPU spikes)
oraz natywnych wywołań User32 C-API dla natychmiastowej reakcji na kliknięcia.
"""
import ctypes
import json
import subprocess
import sys
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


def media_play_pause():
    send_media_key(VK_MEDIA_PLAY_PAUSE)


def media_next():
    send_media_key(VK_MEDIA_NEXT_TRACK)


def media_prev():
    send_media_key(VK_MEDIA_PREV_TRACK)


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

    def run(self):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # Ukryte okno PowerShell

        try:
            self.process = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_DAEMON_SCRIPT],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                startupinfo=startupinfo,
                bufsize=1
            )

            while self.running and self.process and self.process.poll() is None:
                line = self.process.stdout.readline()
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

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
            self.process = None
        self.wait(1000)
