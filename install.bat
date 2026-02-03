@echo off
chcp 65001 >nul

echo ═══════════════════════════════════════════════════════
echo   가상환경 설치
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
    exit /b 1
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
pause
