@echo off
title DONG GOI UPDATER.EXE
echo ====================================================
echo        DANG DONG GOI MASTER TOOL HUB UPDATER
echo ====================================================
python -m PyInstaller --onefile --windowed --name Updater --icon app_icon.ico --distpath . updater\updater_main.py --noconfirm
echo Hoan tat dong goi Updater.exe!
pause
