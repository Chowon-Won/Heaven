@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==============================================
echo  SisFaCon AutoFacturador - Instalacion
echo ==============================================
where py >nul 2>nul
if errorlevel 1 (
  echo No se encontro Python. Instale Python 3.12 desde https://www.python.org/downloads/
  echo Marque "Add python.exe to PATH" durante la instalacion.
  pause
  exit /b 1
)
if not exist .venv (
  echo Creando entorno virtual...
  py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
if errorlevel 1 (
  echo.
  echo ERROR al instalar dependencias. Revise su conexion a Internet.
  pause
  exit /b 1
)
echo.
echo Instalacion terminada. Use ejecutar.bat para abrir el programa.
pause
