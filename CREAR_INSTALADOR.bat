@echo off
cd /d "%~dp0"
echo ==========================================================
echo  SisFaCon AutoFacturador - Crear instalador (.exe)
echo ==========================================================
echo Este proceso descarga lo necesario y genera:
echo    build\salida\SisFaConAutoFacturador_Setup_1.0.0.exe
echo Necesita Internet. Tarda entre 5 y 15 minutos la primera vez.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build\crear_instalador.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: no se pudo crear el instalador. Revise el mensaje de arriba.
)
echo.
pause
