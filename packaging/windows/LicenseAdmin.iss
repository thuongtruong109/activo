; Build with tools/release/windows.ps1. User data is never part of [Files] or deletion rules.
#ifndef PayloadDir
  #error PayloadDir is required
#endif
#ifndef ReleaseVersion
  #error ReleaseVersion is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef InstallerId
  #define InstallerId "Activo.LicenseAdmin"
#endif
#ifndef Publisher
  #define Publisher GetStringFileInfo(PayloadDir + "\LicenseAdmin.exe", "CompanyName")
#endif
#ifndef ProductName
  #define ProductName GetStringFileInfo(PayloadDir + "\LicenseAdmin.exe", "ProductName")
#endif
#ifndef CopyrightText
  #define CopyrightText GetStringFileInfo(PayloadDir + "\LicenseAdmin.exe", "LegalCopyright")
#endif

[Setup]
AppId={#InstallerId}
AppName={#ProductName}
AppVersion={#ReleaseVersion}
AppPublisher={#Publisher}
AppCopyright={#CopyrightText}
VersionInfoVersion={#ReleaseVersion}
VersionInfoProductName={#ProductName}
VersionInfoProductVersion={#ReleaseVersion}
VersionInfoCompany={#Publisher}
DefaultDirName={localappdata}\Programs\Activo\LicenseAdmin
DefaultGroupName=Activo\License Admin
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=LicenseAdmin-{#ReleaseVersion}-windows-x64-setup
SetupIconFile=..\..\license_admin\assets\app.ico
UninstallDisplayIcon={app}\LicenseAdmin.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=LicenseAdmin.exe
RestartApplications=no
Uninstallable=yes
DisableProgramGroupPage=yes
#ifdef Signing
SignTool=activo
SignedUninstaller=yes
#else
SignedUninstaller=no
#endif

[Files]
Source: "{#PayloadDir}\LicenseAdmin.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\sbom.cdx.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\docs\WINDOWS_RELEASE.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\License Admin"; Filename: "{app}\LicenseAdmin.exe"; AppUserModelID: "LicenseTools.LicenseAdmin"
Name: "{group}\Uninstall License Admin"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\LicenseAdmin.exe"; Description: "Launch License Admin"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  InstalledVersion: String;
  InstalledPackedVersion, CandidatePackedVersion: Int64;
begin
  Result := '';
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#InstallerId}_is1',
      'DisplayVersion', InstalledVersion) then
  begin
    if (not StrToVersion(InstalledVersion, InstalledPackedVersion)) or
       (not StrToVersion('{#ReleaseVersion}', CandidatePackedVersion)) then
    begin
      Result := 'Cannot compare installed and candidate versions. Repair the uninstall registration before updating.';
      Exit;
    end;
    if ComparePackedVersion(InstalledPackedVersion, CandidatePackedVersion) > 0 then
    begin
      if ExpandConstant('{param:ALLOWDOWNGRADE|0}') <> '1' then
        Result := 'A newer License Admin version is installed. Back up your project data and verify schema compatibility before an explicit rollback using /ALLOWDOWNGRADE=1.';
    end;
  end;
end;
