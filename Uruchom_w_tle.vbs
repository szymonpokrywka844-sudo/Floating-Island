Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)

pyw = "pythonw.exe"
p0 = "C:\Users\Szymon\AppData\Local\Python\pythoncore-3.15-64\pythonw.exe"
p1 = "C:\Users\Szymon\AppData\Local\Python\bin\pythonw.exe"
p2 = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Python\bin\pythonw.exe")
p3 = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python315\pythonw.exe")

If fso.FileExists(p0) Then
    pyw = p0
ElseIf fso.FileExists(p1) Then
    pyw = p1
ElseIf fso.FileExists(p2) Then
    pyw = p2
ElseIf fso.FileExists(p3) Then
    pyw = p3
End If

WshShell.Run """" & pyw & """ """ & strDir & "\main.py""", 0, False
