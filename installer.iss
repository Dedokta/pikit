; Inno Setup script for PiKit
; Build after running: pyinstaller pikit.spec

[Setup]
AppName=PiKit
AppVersion=1.0.33
AppPublisher=Illuminart
AppPublisherURL=https://illuminart.com.au
DefaultDirName={autopf}\PiKit
DefaultGroupName=PiKit
OutputDir=installer_out
OutputBaseFilename=PiKit_Setup_1.0.33
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
; PiKit requires elevation — launching from Start Menu will trigger UAC normally.
; Auto-launch from installer is disabled to avoid elevation conflict (error 740).

[UninstallDelete]
; Remove AppData settings on uninstall (optional — comment out to preserve)
; Type: filesandordirs; Name: "{userappdata}\PiKit"
