[Setup]
AppName=Absensi Kiosk SMK
AppVersion=1.0
DefaultDirName={autopf}\AbsensiKiosk
DefaultGroupName=Absensi Kiosk
OutputDir=Output
OutputBaseFilename=AbsensiKiosk-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
SetupIconFile=

[Files]
Source: "dist\AbsensiKiosk.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\Absensi Kiosk"; Filename: "{app}\AbsensiKiosk.exe"
Name: "{userstartup}\Absensi Kiosk"; Filename: "{app}\AbsensiKiosk.exe"

[Run]
Filename: "notepad.exe"; Parameters: "{app}\.env"; Description: "Edit konfigurasi device sebelum pertama kali jalan"; Flags: postinstall
