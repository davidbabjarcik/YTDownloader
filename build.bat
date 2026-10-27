@echo off
setlocal
cd /d "%~dp0"
echo === YT Downloader build ===

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ was not found in PATH. Install it from python.org first.
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  python -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :fail
pip install -r requirements.txt pyinstaller || goto :fail

echo.
echo --- Fetching yt-dlp and FFmpeg (one time, ~150 MB) ---
python tools\fetch_deps.py bin || goto :fail

echo.
echo --- Building YTDownloader.exe ---
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
set ICON=
if exist assets\icon.ico set ICON=--icon assets\icon.ico
pyinstaller --noconfirm --clean --onefile --windowed --name YTDownloader %ICON% main.py || goto :fail

mkdir dist\bin
copy /y bin\*.exe dist\bin\ >nul

echo.
echo --- Creating portable zip ---
powershell -NoProfile -Command "Compress-Archive -Path 'dist\YTDownloader.exe','dist\bin' -DestinationPath 'dist\YTDownloader-portable.zip' -Force"

echo.
echo DONE.  dist\YTDownloader.exe  (keep the "bin" folder next to it)
echo        dist\YTDownloader-portable.zip
exit /b 0

:fail
echo.
echo BUILD FAILED.
exit /b 1
