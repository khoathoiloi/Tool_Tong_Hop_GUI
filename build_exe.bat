@echo off
title DONG GOI EXE - MASTER TOOL GUI
cd /d "%~dp0"
echo =====================================================================
echo    DANG DONG GOI THANH FILE EXE DUY NHAT BANG PYINSTALLER...
echo =====================================================================
pyinstaller --noconfirm --onedir --windowed ^
    --name "MasterToolHub" ^
    --icon "app_icon.ico" ^
    --add-data "core;core" ^
    --add-data "modules;modules" ^
    --add-data "app_icon.ico;." ^
    app.py

echo.
echo =====================================================================
echo   DONG GOI HOAN TAT! File EXE nam tai: dist\MasterToolHub\MasterToolHub.exe
echo =====================================================================
pause