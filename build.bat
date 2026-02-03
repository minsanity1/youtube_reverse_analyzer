@echo off
chcp 65001 >nul

echo ═══════════════════════════════════════════════════════
echo   EXE 빌드
echo ═══════════════════════════════════════════════════════
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] 가상환경이 없습니다. 먼저 install.bat을 실행하세요.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [1/2] PyInstaller로 빌드 중...
pyinstaller --noconfirm --onefile --windowed ^
    --name "YouTubeDownloader" ^
    --add-data "channel_video_meta.py;." ^
    download_thumbnails_gui.py

if errorlevel 1 (
    echo [ERROR] 빌드 실패
    pause
    exit /b 1
)

echo.
echo ═══════════════════════════════════════════════════════
echo   빌드 완료!
echo   결과물: dist\YouTubeDownloader.exe
echo ═══════════════════════════════════════════════════════
pause
