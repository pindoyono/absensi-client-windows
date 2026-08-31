[Setup]
AppName=ABSENKU
AppVersion=1.0
DefaultDirName={autopf}\ABSENKU
DefaultGroupName=ABSENKU
OutputDir=Output
OutputBaseFilename=ABSENSIKU-V1
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
SetupIconFile=

[Files]
Source: "dist\ABSENKU.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\ABSENKU"; Filename: "{app}\ABSENKU.exe"
Name: "{userstartup}\ABSENKU"; Filename: "{app}\ABSENKU.exe"

[Run]
Filename: "notepad.exe"; Parameters: "{app}\.env"; Description: "Edit konfigurasi device sebelum pertama kali jalan"; Flags: postinstall
