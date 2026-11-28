; Windows-installer (Setup.exe) voor Microsoft 365 beheer, gemaakt met Inno Setup 6.
; Wordt aangeroepen door bouwen.py:  ISCC.exe /DVersie=2.5.0 /DBron=<map met de app> /O<uitvoermap> M365Beheer.iss
;
; - Installeert per gebruiker (geen beheerdersrechten nodig) in dezelfde map als de PowerShell-installer,
;   zodat de ingebouwde updater gewoon blijft werken.
; - Snelkoppelingen in het Startmenu en (optioneel) op het bureaublad; verwijderen via Instellingen > Apps.
; - Een eerdere installatie met de PowerShell-installer wordt netjes overgenomen.

#ifndef Versie
  #define Versie "0.0.0"
#endif
#ifndef Bron
  #error Geef de map met de gebouwde app op met /DBron=...
#endif

#define Exe "Microsoft 365 beheer.exe"
; /DTest: aparte testinstallatie (eigen naam, map en vermelding), raakt een echte installatie niet
#ifdef Test
  #define Naam "Microsoft 365 beheer TEST"
  #define AppSleutel "JustdataM365BeheerTest"
#else
  #define Naam "Microsoft 365 beheer"
  #define AppSleutel "JustdataM365Beheer"
#endif

[Setup]
AppId={#AppSleutel}
AppName={#Naam}
AppVersion={#Versie}
AppVerName={#Naam} {#Versie}
AppPublisher=Justdata BV
AppPublisherURL=https://m365admin.justsecure.nl/download/
VersionInfoVersion={#Versie}
VersionInfoCompany=Justdata BV
VersionInfoDescription={#Naam} installatie
DefaultDirName={localappdata}\Programs\Justdata\{#Naam}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputBaseFilename=Microsoft-365-beheer-{#Versie}-Setup
SetupIconFile=..\assets\icoon.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Naam}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"

[Tasks]
Name: "bureaublad"; Description: "Snelkoppeling op het bureaublad"; GroupDescription: "Snelkoppelingen:"

#ifndef Test
[InstallDelete]
; Oude programmabestanden weg, zodat er geen restanten van een vorige versie blijven staan
Type: filesandordirs; Name: "{app}\_internal"
; Restanten van de PowerShell-installer
Type: files; Name: "{localappdata}\Programs\Justdata\M365Beheer-verwijderen.ps1"
#endif

[Files]
Source: "{#Bron}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#Naam}"; Filename: "{app}\{#Exe}"; WorkingDir: "{app}"; Comment: "{#Naam} (Justdata)"
Name: "{userdesktop}\{#Naam}"; Filename: "{app}\{#Exe}"; WorkingDir: "{app}"; Comment: "{#Naam} (Justdata)"; Tasks: bureaublad

#ifndef Test
[Registry]
; De vermelding van de PowerShell-installer vervalt: Inno Setup maakt zijn eigen vermelding in Instellingen > Apps
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\JustdataM365Beheer"; Flags: deletekey
#endif

[Run]
Filename: "{app}\{#Exe}"; Description: "{#Naam} nu starten"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM ""{#Exe}"""; Flags: runhidden; RunOnceId: "AppSluiten"

[UninstallDelete]
; Ook bestanden die de updater later heeft neergezet
Type: filesandordirs; Name: "{app}"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { Draait de app nog, dan eerst afsluiten (anders kunnen bestanden niet vervangen worden) }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM "{#Exe}"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(500);
  Result := '';
end;
