; Inno Setup script for MultyCapture
; Build:  iscc /DMyAppVersion=%VERSION% installer\windows\multycapture.iss
;   where  VERSION=$(sh installer/version.sh)
; Expects the PyInstaller one-folder bundle at dist\MultyCapture\ (repo root).

; No default. The preprocessor cannot read multycapture.__version__, so the
; only honest options are to be told the version or to refuse to build — and a
; literal here is exactly what let an installer label itself 0.1.0 while the
; application inside it reported something else.
#ifndef MyAppVersion
  #error Pass /DMyAppVersion=x.y.z — take the number from: sh installer/version.sh
#endif
#define MyAppName "MultyCapture"
#define MyAppPublisher "MultyCapture"
#define MyAppExeName "MultyCapture.exe"

[Setup]
AppId={{7F3B2C10-1E4D-4B7A-9E2F-9C1A2B3C4D5E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=Output
OutputBaseFilename=MultyCapture-Setup-{#MyAppVersion}
SetupIconFile=..\..\packaging\assets\multycapture.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start {#MyAppName} automatically when Windows starts"; Flags: unchecked

[Files]
; Bundle the entire PyInstaller one-folder output.
Source: "..\..\dist\MultyCapture\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; Optional run-at-startup: a shortcut in the common Startup folder (matches the
; admin install mode, unlike a per-user HKCU key).
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; \
  Flags: nowait postinstall skipifsilent
