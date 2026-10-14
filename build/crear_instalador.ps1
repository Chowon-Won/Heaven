# Genera build\salida\SisFaConAutoFacturador_Setup_1.0.0.exe
# Compatible con Windows PowerShell 5.1 (incluido en Windows 10/11).
# Descarga e instala lo necesario para COMPILAR (Python, Inno Setup); el
# instalador resultante no necesita Python en el equipo de destino.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Build = $PSScriptRoot
$Root = Split-Path $Build -Parent
$Cache = Join-Path $Build 'descargas'
$Redist = Join-Path $Build 'redist'
New-Item -ItemType Directory -Force -Path $Cache, $Redist, (Join-Path $Redist 'tessdata') | Out-Null

$PythonUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
$InnoUrl = 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe'
$TessUrl = 'https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe'
$TessData = 'https://github.com/tesseract-ocr/tessdata_fast/raw/main'

function Paso($n, $texto) { Write-Host ''; Write-Host "[$n/7] $texto" -ForegroundColor Cyan }

function Descargar($url, $destino) {
    if (Test-Path $destino) { return }
    Write-Host "   Descargando $(Split-Path $destino -Leaf)..."
    $tmp = "$destino.part"
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
    Move-Item $tmp $destino -Force
}

function Ejecutar($exe, [string[]]$argumentos) {
    & $exe @argumentos
    if ($LASTEXITCODE -ne 0) { throw "Falló: $exe $($argumentos -join ' ') (código $LASTEXITCODE)" }
}

# ---------------------------------------------------------------- 1. Python
Paso 1 'Python 3.12 (solo para compilar)'
$Python = $null
if ($env:PYTHON_EXE -and (Test-Path $env:PYTHON_EXE)) { $Python = $env:PYTHON_EXE }
if (-not $Python) { foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                 "$env:ProgramFiles\Python312\python.exe")) {
    if (Test-Path $c) { $Python = $c; break }
} }
if (-not $Python) {
    try { $p = & py -3.12 -c "import sys; print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $p) { $Python = $p.Trim() } } catch {}
}
if (-not $Python) {
    $inst = Join-Path $Cache 'python-3.12.10-amd64.exe'
    Descargar $PythonUrl $inst
    Write-Host '   Instalando Python para el usuario actual...'
    Start-Process -FilePath $inst -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=0', 'Include_test=0' -Wait
    $Python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $Python)) { throw 'No se pudo instalar Python.' }
}
Write-Host "   Usando $Python"

# ---------------------------------------------------------- 2. dependencias
Paso 2 'Entorno de compilación y dependencias'
$Venv = Join-Path $Build 'venv'
if (-not (Test-Path "$Venv\Scripts\python.exe")) { Ejecutar $Python @('-m', 'venv', $Venv) }
$VPy = "$Venv\Scripts\python.exe"
Ejecutar $VPy @('-m', 'pip', 'install', '--upgrade', 'pip', '--quiet')
Ejecutar $VPy @('-m', 'pip', 'install', '-r', "$Root\requirements.txt", 'pyinstaller>=6.3', '--quiet')

# ------------------------------------------------------------- 3. pruebas
Paso 3 'Pruebas automáticas'
Push-Location $Root
try { Ejecutar $VPy @('-m', 'unittest', 'discover', '-s', 'tests\unit', '-t', '.') }
finally { Pop-Location }

# ---------------------------------------------------------- 4. PyInstaller
Paso 4 'Empaquetando el programa (PyInstaller)'
Push-Location $Root
try {
    Ejecutar $VPy @('-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
        '--name', 'SisFaConAutoFacturador',
        '--icon', "$Build\icono.ico",
        '--add-data', "$Root\plantillas;plantillas",
        '--collect-submodules', 'pywinauto',
        '--hidden-import', 'win32gui', '--hidden-import', 'win32api', '--hidden-import', 'pythoncom',
        '--distpath', "$Build\dist", '--workpath', "$Build\work", '--specpath', $Build,
        "$Root\main.py")
} finally { Pop-Location }
if (-not (Test-Path "$Build\dist\SisFaConAutoFacturador\SisFaConAutoFacturador.exe")) { throw 'PyInstaller no generó el ejecutable.' }

# ------------------------------------------------- 5. componentes externos
Paso 5 'Descargando Tesseract OCR e idiomas'
Descargar $TessUrl (Join-Path $Redist 'tesseract-setup.exe')
Descargar "$TessData/spa.traineddata" (Join-Path $Redist 'tessdata\spa.traineddata')
Descargar "$TessData/eng.traineddata" (Join-Path $Redist 'tessdata\eng.traineddata')

# Tesseract se incluye DENTRO del programa (carpeta tesseract\): se extrae el
# instalador con 7-Zip, así no depende de que la instalación aparte funcione.
$TessDir = Join-Path $Redist 'tesseract'
if (-not (Test-Path "$TessDir\tesseract.exe")) {
    $SevenZip = $null
    foreach ($c in @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe")) {
        if (Test-Path $c) { $SevenZip = $c; break }
    }
    if (-not $SevenZip) { $cmd = Get-Command 7z -ErrorAction SilentlyContinue; if ($cmd) { $SevenZip = $cmd.Source } }
    if (-not $SevenZip) { throw 'Se necesita 7-Zip (https://www.7-zip.org) para incluir Tesseract en el instalador.' }
    if (Test-Path $TessDir) { Remove-Item $TessDir -Recurse -Force }
    Ejecutar $SevenZip @('x', (Join-Path $Redist 'tesseract-setup.exe'), "-o$TessDir", '-y', '-bso0', '-bsp0')
    Get-ChildItem $TessDir -Directory -Filter '$*' | Remove-Item -Recurse -Force
    Get-ChildItem $TessDir -File -Filter 'uninstall*' | Remove-Item -Force
}
if (-not (Test-Path "$TessDir\tesseract.exe")) { throw 'No se pudo extraer tesseract.exe del instalador de Tesseract.' }
Write-Host "   Comprobando Tesseract incluido..."
$env:TESSDATA_PREFIX = (Join-Path $Redist 'tessdata')
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$ver = & "$TessDir\tesseract.exe" --version 2>&1 | Select-Object -First 1
Write-Host "   $ver"
$langs = (& "$TessDir\tesseract.exe" --list-langs 2>&1) -join ' '
if ($langs -notmatch 'spa') { throw "Tesseract incluido no encuentra el idioma español: $langs" }
$ErrorActionPreference = $prevEap
Remove-Item Env:TESSDATA_PREFIX

# ------------------------------------------------------------ 6. Inno Setup
Paso 6 'Inno Setup (creador del instalador)'
function Buscar-ISCC {
    foreach ($d in @("${env:ProgramFiles(x86)}\Inno Setup 7", "$env:ProgramFiles\Inno Setup 7",
                     "${env:ProgramFiles(x86)}\Inno Setup 6", "$env:ProgramFiles\Inno Setup 6",
                     "$env:LOCALAPPDATA\Programs\Inno Setup 7", "$env:LOCALAPPDATA\Programs\Inno Setup 6")) {
        if (Test-Path "$d\ISCC.exe") { return "$d\ISCC.exe" }
    }
    return $null
}
$Iscc = Buscar-ISCC
if (-not $Iscc) {
    $inst = Join-Path $Cache 'innosetup-7.1.0-x64.exe'
    Descargar $InnoUrl $inst
    Write-Host '   Instalando Inno Setup (puede pedir permiso de administrador)...'
    Start-Process -FilePath $inst -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait
    $Iscc = Buscar-ISCC
    if (-not $Iscc) { throw 'No se encontró ISCC.exe tras instalar Inno Setup.' }
}
Write-Host "   Usando $Iscc"

# --------------------------------------------------------- 7. instalador
Paso 7 'Creando el instalador'
Ejecutar $Iscc @('/Q', "$Build\SisFaConAutoFacturador.iss")
$Setup = Get-ChildItem "$Build\salida\SisFaConAutoFacturador_Setup_*.exe" | Sort-Object LastWriteTime | Select-Object -Last 1
Write-Host ''
Write-Host "LISTO: $($Setup.FullName)" -ForegroundColor Green
Write-Host "Tamaño: $([math]::Round($Setup.Length / 1MB, 1)) MB"
if (-not $env:CI) { Start-Process explorer.exe "/select,`"$($Setup.FullName)`"" }
