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
; Seuls les .exe comptent : d'autres applications (ex. Bionic) chargent des DLL de ce dossier et ne peuvent pas être fermées,
; ce qui faisait abandonner toute la mise à jour.
CloseApplicationsFilter=*.exe
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
// Les DLL que d'autres applications (Bionic...) peuvent garder chargées : on les met de côté (renommer est permis
// même quand elles sont utilisées), l'installation écrit alors les nouvelles sans conflit.
const
  LockedDlls = 'VCRUNTIME140.dll|VCRUNTIME140_1.dll|MSVCP140.dll|MSVCP140_1.dll|MSVCP140_2.dll|CONCRT140.dll|dbghelp.dll|dbgcore.dll';

procedure EachLockedDll(Mode: Integer);
var
  List, Name, Path: String;
  P: Integer;
begin
  List := LockedDlls + '|';
  while List <> '' do
  begin
    P := Pos('|', List);
    Name := Copy(List, 1, P - 1);
    List := Copy(List, P + 1, Length(List));
    Path := ExpandConstant('{app}\_internal\') + Name;
    if Mode = 0 then
    begin                                   // avant l'installation : mettre de côté
      DeleteFile(Path + '.old');
      if FileExists(Path) then RenameFile(Path, Path + '.old');
    end
    else if Mode = 1 then
    begin                                   // échec : remettre l'ancienne si la nouvelle n'est pas là
      if (not FileExists(Path)) and FileExists(Path + '.old') then RenameFile(Path + '.old', Path);
    end
    else
      DeleteFile(Path + '.old');            // succès : nettoyer (ignoré si encore utilisée)
  end;
end;

procedure KillJimmy();
var
  rc: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Jimmy.exe', '', SW_HIDE, ewWaitUntilTerminated, rc);
  Sleep(1500);
end;

var
  IsUpgrade: Boolean;

function InitializeSetup(): Boolean;
begin
  IsUpgrade := RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B7E1D6A2-5C0F-4E2B-9B7A-6E8F1A2C3D40}_is1')
            or RegKeyExists(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B7E1D6A2-5C0F-4E2B-9B7A-6E8F1A2C3D40}_is1');
  // Mise à jour discrète : l'ancien Jimmy s'est déjà fermé tout seul. Les Jimmy.exe sans fenêtre qui restent
  // (serveur d'autorisation ou mémoire lancés par une tâche de Claude) ne se ferment pas et bloqueraient tout : on les arrête
  // AVANT que Windows cherche les applications à fermer.
  if IsUpgrade and WizardSilent then
    KillJimmy();
  Result := True;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := IsUpgrade and ((PageID = wpWelcome) or (PageID = wpSelectDir) or (PageID = wpSelectProgramGroup)
                           or (PageID = wpSelectTasks) or (PageID = wpReady));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    KillJimmy();
    EachLockedDll(0);
  end
  else if CurStep = ssPostInstall then
    EachLockedDll(2);
end;

procedure DeinitializeSetup();
begin
  EachLockedDll(1);
end;
