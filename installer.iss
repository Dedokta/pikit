; Inno Setup script for PiKit
; Build after running: pyinstaller pikit.spec

[Setup]
AppName=PiKit
AppVersion=1.1.2
AppPublisher=Illuminart
AppPublisherURL=https://illuminart.com.au
DefaultDirName={autopf}\PiKit
DefaultGroupName=PiKit
OutputDir=installer_out
OutputBaseFilename=PiKit_Setup_1.1.2
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
; SetupIconFile=assets\pikit.ico  ; add a pikit.ico to assets\ to enable
UninstallDisplayIcon={app}\PiKit.exe
; Request admin — needed for raw disk access
PrivilegesRequired=admin
; Minimum Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Copy the entire PyInstaller onedir output
Source: "dist\PiKit\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PiKit"; Filename: "{app}\PiKit.exe"
Name: "{group}\Uninstall PiKit"; Filename: "{uninstallexe}"
Name: "{commondesktop}\PiKit"; Filename: "{app}\PiKit.exe"; Tasks: desktopicon

[Run]
; shellexec invokes ShellExecute which handles UAC elevation correctly.
; skipifsilent prevents double-launch during auto-updates (/VERYSILENT).
Filename: "{app}\PiKit.exe"; Description: "Launch PiKit"; Flags: postinstall nowait skipifsilent shellexec
; Relaunch after a silent in-app update (replaces the old update .bat).
; Only when the updater passes /PIKITRELAUNCH, so scripted silent installs don't launch the app.
Filename: "{app}\PiKit.exe"; Flags: nowait skipifnotsilent shellexec; Check: IsAutoUpdate

[UninstallDelete]
; Remove AppData settings on uninstall (optional — comment out to preserve)
; Type: filesandordirs; Name: "{userappdata}\PiKit"

[Code]
function IsAutoUpdate: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/PIKITRELAUNCH') = 0 then
      Result := True;
end;