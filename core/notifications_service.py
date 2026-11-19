"""
Serwis nasłuchujący powiadomień systemowych Windows (Windows.UI.Notifications).
Przechwytuje w czasie rzeczywistym powiadomienia z:
- Łącza z telefonem (Phone Link): SMS-y, połączenia przychodzące, WhatsApp z telefonu
- Komunikatorów (Discord, Slack, Messenger, Teams)
- Gier (Steam, Epic Games, Xbox)
- Przeglądarek, systemu Windows, sklepu Microsoft Store

Typy zdarzeń emitowane przez notification_arrived:
  kind="sms"      - wiadomość SMS z telefonu
  kind="call"     - połączenie przychodzące z telefonu
  kind="discord"  - powiadomienie Discord
  kind="steam"    - powiadomienie Steam
  kind="generic"  - pozostałe aplikacje
"""
import json
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal

# Klucze słownikowe aplikacji Phone Link w różnych wersjach systemu
PHONE_LINK_APP_KEYS = {
    "phone link": "phone",
    "łącze z telefonem": "phone",
    "your phone": "phone",
    "twój telefon": "phone",
    "yourphone": "phone",
}

DISCORD_KEYS = {"discord"}
STEAM_KEYS = {"steam"}
TEAMS_KEYS = {"microsoft teams", "teams"}
XBOX_KEYS = {"xbox", "game bar"}

POWERSHELL_NOTIF_SCRIPT = r'''
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

try {
    [Windows.UI.Notifications.Management.UserNotificationListener,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null
    [Windows.UI.Notifications.NotificationKinds,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null
    $listener = [Windows.UI.Notifications.Management.UserNotificationListener]::Current
    $kind = [Windows.UI.Notifications.NotificationKinds]::Toast

    $op = $listener.GetNotificationsAsync($kind)
    $notifs = Await-WinRT $op ([System.Collections.Generic.IReadOnlyList[Windows.UI.Notifications.UserNotification]])
    $lastMaxId = 0
    if ($notifs.Count -gt 0) {
        $lastMaxId = ($notifs | Measure-Object -Property Id -Maximum).Maximum
    }

    [Console]::WriteLine("READY|$lastMaxId")

    while ($true) {
        try {
            $op = $listener.GetNotificationsAsync($kind)
            $notifs = Await-WinRT $op ([System.Collections.Generic.IReadOnlyList[Windows.UI.Notifications.UserNotification]])
            
            if ($notifs.Count -gt 0) {
                $newNotifs = $notifs | Where-Object { $_.Id -gt $lastMaxId }
                foreach ($n in $newNotifs) {
                    $appName = $n.AppInfo.DisplayInfo.DisplayName
                    $appId   = $n.AppInfo.AppUserModelId
                    $texts = @()
                    foreach ($b in $n.Notification.Visual.Bindings) {
                        foreach ($e in $b.GetTextElements()) {
                            if ($e.Text) { $texts += $e.Text }
                        }
                    }

                    $title = if ($texts.Count -gt 0) { $texts[0] } else { $appName }
                    $msg   = if ($texts.Count -gt 1) { $texts[1] } else { "" }

                    # Wykrywanie rodzaju powiadomienia Phone Link (polaczenie vs SMS)
                    $notifKind = "generic"
                    $appLower  = $appName.ToLower()
                    $appIdL    = if ($appId) { $appId.ToLower() } else { "" }
                    $isPhone   = ($appLower -match "phone link|your phone|yourphone|lacze z telefonem|twoj telefon" -or $appIdL -match "yourphone|microsoft\.yourphone")
                    if ($isPhone) {
                        $titleLower = $title.ToLower()
                        $msgLower   = $msg.ToLower()
                        if ($titleLower -match "polaczen|dzwoni|calling|incoming call|odbierz|odrzuc" -or $msgLower -match "calling|incoming") {
                            $notifKind = "call"
                        } else {
                            $notifKind = "sms"
                        }
                    } elseif ($appLower -match "discord") {
                        $notifKind = "discord"
                    } elseif ($appLower -match "steam") {
                        $notifKind = "steam"
                    } elseif ($appLower -match "teams") {
                        $notifKind = "teams"
                    } elseif ($appLower -match "xbox|game bar") {
                        $notifKind = "xbox"
                    }

                    $obj = @{
                        id      = $n.Id
                        app     = $appName
                        app_id  = if ($appId) { $appId } else { "" }
                        title   = $title
                        message = $msg
                        kind    = $notifKind
                    }
                    [Console]::WriteLine("NOTIF|" + ($obj | ConvertTo-Json -Compress))
                    if ($n.Id -gt $lastMaxId) {
                        $lastMaxId = $n.Id
                    }
                }
            }
        } catch {}
        Start-Sleep -Milliseconds 800
    }
} catch {
    [Console]::WriteLine("ERROR|" + $_.Exception.Message)
}
'''


class NotificationMonitorWorker(QThread):
    """Wątek w tle nasłuchujący nowych powiadomień Windows w czasie rzeczywistym."""
    notification_arrived = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.running = True

    def run(self):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

        try:
            self.process = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_NOTIF_SCRIPT],
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
                    if line.startswith("NOTIF|"):
                        json_str = line[6:]
                        try:
                            data = json.loads(json_str)
                            # Uzupełnij kind jeśli brak (starszy skrypt)
                            if "kind" not in data:
                                data["kind"] = _classify_notif(data)
                            self.notification_arrived.emit(data)
                        except Exception:
                            pass
        except Exception as e:
            print(f"[NotifWorker Error] {e}")

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
            self.process = None
        self.wait(1000)


def _classify_notif(data: dict) -> str:
    """Klasyfikuje powiadomienie na podstawie nazwy aplikacji (fallback po stronie Python)."""
    app = data.get("app", "").lower()
    title = data.get("title", "").lower()
    msg = data.get("message", "").lower()

    is_phone = any(k in app for k in PHONE_LINK_APP_KEYS)
    if is_phone:
        call_words = ("dzwoni", "połączen", "calling", "incoming call", "odbierz")
        if any(w in title or w in msg for w in call_words):
            return "call"
        return "sms"

    if "discord" in app:
        return "discord"
    if "steam" in app:
        return "steam"
    if "teams" in app:
        return "teams"
    if "xbox" in app or "game bar" in app:
        return "xbox"
    return "generic"
