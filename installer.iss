; ===================================================================
; Skrypt instalatora Inno Setup 7 dla Floating Island
; ===================================================================

#define MyAppName "Floating Island"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Szymon"
#define MyAppExeName "Uruchom_w_tle.vbs"
#define MyAppIcon "island_icon.ico"

[Setup]
AppId={{8B17FA3C-91B4-4B42-9908-168532F42D1C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer_output
OutputBaseFilename=FloatingIsland_Setup
SetupIconFile={#MyAppIcon}
SolidCompression=yes
Compression=lzma2/ultra64
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppIcon}

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Utworz skrot na Pulpicie"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "autostart"; Description: "Uruchamiaj Floating Island przy starcie systemu Windows"; GroupDescription: "Opcje uruchamiania:"; Flags: checkedonce

[Files]
Source: "main.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "start.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Uruchom_w_tle.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "island_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "version.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "core\*"; DestDir: "{app}\core"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__,*.pyc"
Source: "ui\*"; DestDir: "{app}\ui"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__,*.pyc"
Source: "modules\*"; DestDir: "{app}\modules"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__,*.pyc"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIcon}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\{#MyAppExeName}"""; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIcon}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "FloatingIsland"; ValueData: """{sys}\wscript.exe"" ""{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\{#MyAppExeName}"""; Description: "Uruchom Floating Island po zakonczeniu instalacji"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\core\__pycache__"
Type: filesandordirs; Name: "{app}\ui\__pycache__"
Type: filesandordirs; Name: "{app}\modules\__pycache__"
Type: files; Name: "{app}\*.pyc"
Type: files; Name: "{app}\error.log"

[Code]
procedure KillRunningApp();
var
  ResultCode: Integer;
begin
  Exec('powershell.exe', '-NoProfile -Command "if (Test-Path ''$env:TEMP\floating_island.pid'') { $idText = (Get-Content ''$env:TEMP\floating_island.pid'' -Raw).Trim(); if ($idText -match ''^\d+$'') { $id = [int]$idText; $p = Get-CimInstance Win32_Process -Filter (''ProcessId = '' + $id); if ($p -and ($p.Name -eq ''python.exe'' -or $p.Name -eq ''pythonw.exe'') -and $p.CommandLine -match ''(?i)Floating island.*main\.py'') { Get-CimInstance Win32_Process -Filter (''ParentProcessId = '' + $id) | Where-Object { $_.Name -eq ''powershell.exe'' -and $_.CommandLine -match ''GlobalSystemMediaTransportControlsSessionManager|UserNotificationListener'' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } }; Remove-Item ''$env:TEMP\floating_island.pid'' -ErrorAction SilentlyContinue }"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
begin
  KillRunningApp();
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  KillRunningApp();
  Result := True;
end;
