@echo off
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo === Pruebas unitarias (no tocan SisFaCon) ===
python -m pytest tests\unit -v
echo.
echo Para las pruebas de solo lectura contra SisFaCon real:
echo   set SISFACON_REAL=1 ^&^& python -m pytest tests\real -v -s
pause
