"""Read connected Bluetooth device names and battery levels from Windows."""
import json
import subprocess

from PyQt6.QtCore import QThread, pyqtSignal


POWERSHELL_SCRIPT = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await-WinRT($operation, $type) {
    $method = $asTaskGeneric.MakeGenericMethod($type)
    $task = $method.Invoke($null, @($operation))
    $task.Wait()
    return $task.Result
}
[Windows.Devices.Bluetooth.BluetoothDevice,Windows.Devices.Bluetooth,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Enumeration.DeviceInformation,Windows.Devices.Enumeration,ContentType=WindowsRuntime] | Out-Null
$selector = [Windows.Devices.Bluetooth.BluetoothDevice]::GetDeviceSelector()
$last = ''
while ($true) {
    try {
        $items = @()
        $infos = Await-WinRT ([Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync($selector)) ([Windows.Devices.Enumeration.DeviceInformationCollection])
        $pnpDevices = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match '^BTHENUM\\' -and $_.FriendlyName })
        foreach ($info in $infos) {
            try {
                $device = Await-WinRT ([Windows.Devices.Bluetooth.BluetoothDevice]::FromIdAsync($info.Id)) ([Windows.Devices.Bluetooth.BluetoothDevice])
                if (-not $device -or $device.ConnectionStatus.ToString() -ne 'Connected') { continue }

                $levels = @(
                    foreach ($node in $pnpDevices) {
                        if (-not $node.FriendlyName.StartsWith($device.Name, [System.StringComparison]::OrdinalIgnoreCase)) { continue }
                        $property = Get-PnpDeviceProperty -InstanceId $node.InstanceId `
                            -KeyName '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2' `
                            -ErrorAction SilentlyContinue
                        if ($property -and $null -ne $property.Data) {
                            $level = [int]$property.Data
                            if ($level -ge 0 -and $level -le 100) { $level }
                        }
                    }
                )
                if ($levels.Count -gt 0) {
                    $items += [PSCustomObject]@{ name = $device.Name; battery = [int]$levels[0] }
                }
            } catch {
                continue
            }
        }
        $json = ConvertTo-Json -InputObject @($items) -Compress
        if ($json -ne $last) {
            $last = $json
            [Console]::WriteLine($json)
        }
    } catch {
        if ($last -ne '[]') {
            $last = '[]'
            [Console]::WriteLine('[]')
        }
    }
    Start-Sleep -Seconds 8
}
'''


class BluetoothDeviceMonitorWorker(QThread):
    """Poll battery properties exposed by connected Bluetooth PnP devices."""

    devices_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.running = True

    def run(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            self.process = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", POWERSHELL_SCRIPT],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                startupinfo=startupinfo,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                bufsize=1,
            )
            while self.running and self.process.poll() is None:
                line = self.process.stdout.readline()
                if not line:
                    continue
                try:
                    devices = json.loads(line.strip())
                    if isinstance(devices, list):
                        self.devices_changed.emit(devices)
                except (json.JSONDecodeError, TypeError):
                    continue
        except Exception as error:
            print(f"[Bluetooth Monitor Error] {error}")
        finally:
            self.process = None

    def stop(self):
        self.running = False
        process = self.process
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception:
                pass
        self.wait(3000)
