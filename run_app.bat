@echo off
title BO CONG CU TONG HOP FANPAGE & MEDIA (MASTER GUI)
cd /d "%~dp0"
echo =====================================================================
echo    DANG KHOI CHAY BO CONG CU TONG HOP ALL-IN-ONE MASTER GUI (O E:\)
echo =====================================================================
python app.py
if %errorlevel% neq 0 (
    echo.
    echo [!] Gap loi khi chay chuong trinh. Nhan phim bat ky de thoat...
    pause > nul
)