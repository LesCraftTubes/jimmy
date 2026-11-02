; Installateur de Jimmy (Inno Setup 6). Compilation : iscc /DMyAppVersion=1.0.0 installer\jimmy.iss
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={{B7E1D6A2-5C0F-4E2B-9B7A-6E8F1A2C3D40}
AppName=Jimmy
AppVersion={#MyAppVersion}
AppPublisher=Jimmy
DefaultDirName={autopf}\Jimmy
DefaultGroupName=Jimmy
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=Jimmy-Setup-{#MyAppVersion}
SetupIconFile=..\jimmy.ico
UninstallDisplayIcon={app}\Jimmy.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Lancer Jimmy au démarrage de Windows"; GroupDescription: "Options :"; Flags: unchecked

[Files]
Source: "..\dist\Jimmy\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{autoprograms}\Jimmy"; Filename: "{app}\Jimmy.exe"
Name: "{autodesktop}\Jimmy"; Filename: "{app}\Jimmy.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Jimmy"; ValueData: """{app}\Jimmy.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\Jimmy.exe"; Description: "Lancer Jimmy"; Flags: nowait postinstall skipifsilent
