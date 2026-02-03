@echo off
chcp 65001 >nul

echo ═══════════════════════════════════════════════════════
echo   프로그램 실행
echo ═══════════════════════════════════════════════════════
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] 가상환경이 없습니다. 먼저 install.bat을 실행하세요.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python download_thumbnails_gui.py
pause
