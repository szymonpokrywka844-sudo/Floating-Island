"""Windows render endpoint discovery and default-output switching."""
import base64
import json
import subprocess


_POWERSHELL_TEMPLATE = r'''
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$source = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public sealed class FloatingIslandAudioOutput
{
    public string id { get; set; }
    public string name { get; set; }
    public bool is_default { get; set; }
}

public static class FloatingIslandAudio
{
    private enum DataFlow { Render = 0, Capture = 1, All = 2 }
    private enum DeviceRole { Console = 0, Multimedia = 1, Communications = 2 }

    [StructLayout(LayoutKind.Sequential)]
    private struct PropertyKey { public Guid formatId; public uint propertyId; }

    [StructLayout(LayoutKind.Explicit)]
    private struct PropVariant
    {
        [FieldOffset(0)] public ushort type;
        [FieldOffset(8)] public IntPtr stringValue;
    }

    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    private class DeviceEnumeratorClass { }

    [ComImport, Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")]
    private class PolicyConfigClass { }

    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IDeviceEnumerator
    {
        [PreserveSig] int EnumAudioEndpoints(DataFlow flow, int stateMask, out IDeviceCollection devices);
        [PreserveSig] int GetDefaultAudioEndpoint(DataFlow flow, DeviceRole role, out IDevice device);
        [PreserveSig] int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string id, out IDevice device);
        [PreserveSig] int RegisterEndpointNotificationCallback(IntPtr callback);
        [PreserveSig] int UnregisterEndpointNotificationCallback(IntPtr callback);
    }

    [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IDeviceCollection
    {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int Item(uint index, out IDevice device);
    }

    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IDevice
    {
        [PreserveSig] int Activate(ref Guid iid, int classContext, IntPtr activationParams, out IntPtr instance);
        [PreserveSig] int OpenPropertyStore(int access, out IPropertyStore properties);
        [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
        [PreserveSig] int GetState(out int state);
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int GetAt(uint index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropVariant value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropVariant value);
        [PreserveSig] int Commit();
    }

    [ComImport, Guid("F8679F50-850A-41CF-9C72-430F290290C8"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPolicyConfig
    {
        [PreserveSig] int GetMixFormat(string id, IntPtr format);
        [PreserveSig] int GetDeviceFormat(string id, bool isDefault, IntPtr format);
        [PreserveSig] int ResetDeviceFormat(string id);
        [PreserveSig] int SetDeviceFormat(string id, IntPtr format, IntPtr mixFormat);
        [PreserveSig] int GetProcessingPeriod(string id, bool isDefault, IntPtr defaultPeriod, IntPtr minimumPeriod);
        [PreserveSig] int SetProcessingPeriod(string id, IntPtr period);
        [PreserveSig] int GetShareMode(string id, IntPtr mode);
        [PreserveSig] int SetShareMode(string id, IntPtr mode);
        [PreserveSig] int GetPropertyValue(string id, bool store, ref PropertyKey key, out PropVariant value);
        [PreserveSig] int SetPropertyValue(string id, bool store, ref PropertyKey key, ref PropVariant value);
        [PreserveSig] int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string id, DeviceRole role);
        [PreserveSig] int SetEndpointVisibility(string id, bool visible);
    }

    [DllImport("ole32.dll")]
    private static extern int PropVariantClear(ref PropVariant value);

    private static void Check(int result)
    {
        if (result < 0) Marshal.ThrowExceptionForHR(result);
    }

    private static string GetId(IDevice device)
    {
        string id;
        Check(device.GetId(out id));
        return id;
    }

    private static string GetName(IDevice device)
    {
        IPropertyStore store;
        Check(device.OpenPropertyStore(0, out store));
        PropertyKey key = new PropertyKey {
            formatId = new Guid("A45C254E-DF1C-4EFD-8020-67D146A850E0"),
            propertyId = 14
        };
        PropVariant value;
        Check(store.GetValue(ref key, out value));
        try
        {
            if ((value.type == 31 || value.type == 8) && value.stringValue != IntPtr.Zero)
                return Marshal.PtrToStringUni(value.stringValue);
            return "Wyjście audio";
        }
        finally
        {
            PropVariantClear(ref value);
            if (Marshal.IsComObject(store)) Marshal.ReleaseComObject(store);
        }
    }

    public static FloatingIslandAudioOutput[] GetRenderOutputs()
    {
        IDeviceEnumerator enumerator = (IDeviceEnumerator)new DeviceEnumeratorClass();
        IDeviceCollection collection = null;
        IDevice defaultDevice = null;
        List<FloatingIslandAudioOutput> outputs = new List<FloatingIslandAudioOutput>();
        try
        {
            string defaultId = null;
            if (enumerator.GetDefaultAudioEndpoint(DataFlow.Render, DeviceRole.Multimedia, out defaultDevice) >= 0 && defaultDevice != null)
                defaultId = GetId(defaultDevice);
            Check(enumerator.EnumAudioEndpoints(DataFlow.Render, 1, out collection));
            uint count;
            Check(collection.GetCount(out count));
            for (uint index = 0; index < count; index++)
            {
                IDevice device = null;
                try
                {
                    Check(collection.Item(index, out device));
                    string id = GetId(device);
                    outputs.Add(new FloatingIslandAudioOutput {
                        id = id,
                        name = GetName(device),
                        is_default = String.Equals(id, defaultId, StringComparison.OrdinalIgnoreCase)
                    });
                }
                finally
                {
                    if (device != null && Marshal.IsComObject(device)) Marshal.ReleaseComObject(device);
                }
            }
            return outputs.ToArray();
        }
        finally
        {
            if (defaultDevice != null && Marshal.IsComObject(defaultDevice)) Marshal.ReleaseComObject(defaultDevice);
            if (collection != null && Marshal.IsComObject(collection)) Marshal.ReleaseComObject(collection);
            if (Marshal.IsComObject(enumerator)) Marshal.ReleaseComObject(enumerator);
        }
    }

    public static void SetDefaultOutput(string id)
    {
        bool found = false;
        foreach (FloatingIslandAudioOutput output in GetRenderOutputs())
            if (String.Equals(output.id, id, StringComparison.OrdinalIgnoreCase)) found = true;
        if (!found) throw new InvalidOperationException("Wybrane wyjście nie jest już dostępne.");

        IPolicyConfig policy = (IPolicyConfig)new PolicyConfigClass();
        try
        {
            foreach (DeviceRole role in new DeviceRole[] { DeviceRole.Console, DeviceRole.Multimedia, DeviceRole.Communications })
            {
                int result = policy.SetDefaultEndpoint(id, role);
                Check(result);
            }
        }
        finally
        {
            if (Marshal.IsComObject(policy)) Marshal.ReleaseComObject(policy);
        }
    }
}
'@
Add-Type -TypeDefinition $source
__ACTION__
'''


def _run_audio_command(action: str, device_id: str | None = None):
    if action == "list":
        action_script = "[FloatingIslandAudio]::GetRenderOutputs() | ConvertTo-Json -Compress -Depth 3"
    elif action == "set" and device_id:
        encoded_id = base64.b64encode(device_id.encode("utf-8")).decode("ascii")
        action_script = (
            f"$id = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_id}')); "
            "[FloatingIslandAudio]::SetDefaultOutput($id); [Console]::WriteLine('OK')"
        )
    else:
        raise ValueError("Nieprawidłowe polecenie wyjścia audio.")

    script = _POWERSHELL_TEMPLATE.replace("__ACTION__", action_script)
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=12,
        startupinfo=startupinfo,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Windows nie zmienił wyjścia audio."
        raise RuntimeError(message)
    return result.stdout.strip()


def list_audio_outputs() -> list[dict]:
    """Return active Windows playback endpoints and the current default."""
    output = _run_audio_command("list")
    if not output:
        return []
    devices = json.loads(output)
    return devices if isinstance(devices, list) else [devices]


def set_default_audio_output(device_id: str) -> None:
    """Set the selected endpoint as the Windows default for all playback roles."""
    if not device_id:
        raise ValueError("Brak identyfikatora wyjścia audio.")
    _run_audio_command("set", device_id)
