@echo off
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate.bat
pyinstaller --noconfirm --clean --windowed --name SisFaConAutoFacturador ^
  --add-data "plantillas;plantillas" ^
  --collect-submodules pywinauto ^
  --hidden-import win32gui --hidden-import win32api --hidden-import pythoncom ^
  main.py
echo.
echo Ejecutable creado en: dist\SisFaConAutoFacturador\SisFaConAutoFacturador.exe
echo Copie la carpeta completa dist\SisFaConAutoFacturador donde quiera.
pause
