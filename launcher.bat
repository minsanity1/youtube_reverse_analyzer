@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:menu
cls
echo ═══════════════════════════════════════════════════════
echo   YouTube Thumbnail ^& Subtitle Downloader
echo ═══════════════════════════════════════════════════════
echo.
echo   [1] Install   - 가상환경 생성 및 패키지 설치
echo   [2] Run       - 프로그램 실행
echo   [3] Build     - EXE 빌드 (PyInstaller)
echo   [4] Exit      - 종료
echo.
echo ═══════════════════════════════════════════════════════
set /p choice="선택: "

if "%choice%"=="1" goto install
if "%choice%"=="2" goto run
if "%choice%"=="3" goto build
if "%choice%"=="4" goto end
echo 잘못된 선택입니다.
pause
goto menu

:install
cls
echo ═══════════════════════════════════════════════════════
echo   가상환경 설치 중...
echo ═══════════════════════════════════════════════════════
echo.

if exist "venv" (
    echo [!] 기존 가상환경이 존재합니다. 삭제 후 재설치합니다.
    rmdir /s /q venv
)

echo [1/3] 가상환경 생성 중...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Python이 설치되어 있지 않거나 PATH에 등록되지 않았습니다.
    pause
    goto menu
)

echo [2/3] pip 업그레이드 중...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo [3/3] 패키지 설치 중...
pip install PyQt6 requests yt-dlp pyinstaller

echo.
echo ═══════════════════════════════════════════════════════
echo   설치 완료!
echo ═══════════════════════════════════════════════════════
call venv\Scripts\deactivate.bat 2>nul
pause
goto menu

:run
cls
echo ═══════════════════════════════════════════════════════
echo   프로그램 실행 중...
echo ═══════════════════════════════════════════════════════
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] 가상환경이 없습니다. 먼저 Install을 실행하세요.
    pause
    goto menu
)

call venv\Scripts\activate.bat
python download_thumbnails_gui.py
call venv\Scripts\deactivate.bat 2>nul
pause
goto menu

:build
cls
echo ═══════════════════════════════════════════════════════
echo   EXE 빌드 중...
echo ═══════════════════════════════════════════════════════
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] 가상환경이 없습니다. 먼저 Install을 실행하세요.
    pause
    goto menu
)

call venv\Scripts\activate.bat

echo [1/2] PyInstaller로 빌드 중...
pyinstaller --noconfirm --onefile --windowed ^
    --name "YouTubeDownloader" ^
    --add-data "channel_video_meta.py;." ^
    download_thumbnails_gui.py

if errorlevel 1 (
    echo [ERROR] 빌드 실패
    call venv\Scripts\deactivate.bat 2>nul
    pause
    goto menu
)

echo [2/2] 빌드 완료!
echo.
echo ═══════════════════════════════════════════════════════
echo   결과물: dist\YouTubeDownloader.exe
echo ═══════════════════════════════════════════════════════

call venv\Scripts\deactivate.bat 2>nul
pause
goto menu

:end
echo 종료합니다.
exit /b 0
