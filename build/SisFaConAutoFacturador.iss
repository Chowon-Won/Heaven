; Instalador de SisFaCon AutoFacturador (Inno Setup 6.3 o superior).
; Lo genera automáticamente CREAR_INSTALADOR.bat; no hace falta abrirlo a mano.

#define AppName "SisFaCon AutoFacturador"
#define AppVersion "1.0.0"
#define AppExe "SisFaConAutoFacturador.exe"

[Setup]
AppId={{8F3C2A51-6B7D-4E2F-9A1C-5D0E7B3F4A21}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=SisFaCon AutoFacturador
DefaultDirName={autopf}\SisFaCon AutoFacturador
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=salida
OutputBaseFilename=SisFaConAutoFacturador_Setup_{#AppVersion}
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
; Programa (generado por PyInstaller; incluye Python y todas las bibliotecas)
Source: "dist\SisFaConAutoFacturador\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Idiomas OCR español e inglés (los usa el programa aunque Tesseract no los tenga)
Source: "redist\tessdata\*"; DestDir: "{app}\tessdata"; Flags: ignoreversion
; Tesseract OCR incluido en el programa (no necesita instalarse aparte)
Source: "redist\tesseract\*"; DestDir: "{app}\tesseract"; Flags: ignoreversion recursesubdirs createallsubdirs
; Documentación y plantillas
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\plantillas\*"; DestDir: "{app}\plantillas"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Manual de uso"; Filename: "{app}\docs\MANUAL.md"
Name: "{group}\Probar una factura"; Filename: "{app}\docs\PRUEBA_UNA_FACTURA.md"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: postinstall nowait skipifsilent

; Los datos del usuario (escuelas, productos, historial) están en
; %LOCALAPPDATA%\SisFaConAutoFacturador y NO se borran al desinstalar.
