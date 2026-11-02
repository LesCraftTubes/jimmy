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
; Pas de « redémarrage des applications » de Windows (peu fiable) : on relance Jimmy nous-mêmes, voir [Run].
RestartApplications=no

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
; Mise à jour automatique (mode discret) : Jimmy se rouvre tout seul à la fin.
Filename: "{app}\Jimmy.exe"; Flags: nowait runasoriginaluser; Check: WizardSilent

[Code]
// Mise à jour : si Jimmy est déjà installé, on garde le dossier et les options d'avant,
// on ne repose aucune question (bureau, démarrage...).
var
  IsUpgrade: Boolean;

function InitializeSetup(): Boolean;
begin
  IsUpgrade := RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B7E1D6A2-5C0F-4E2B-9B7A-6E8F1A2C3D40}_is1')
            or RegKeyExists(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B7E1D6A2-5C0F-4E2B-9B7A-6E8F1A2C3D40}_is1');
  Result := True;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := IsUpgrade and ((PageID = wpWelcome) or (PageID = wpSelectDir) or (PageID = wpSelectProgramGroup)
                           or (PageID = wpSelectTasks) or (PageID = wpReady));
end;
