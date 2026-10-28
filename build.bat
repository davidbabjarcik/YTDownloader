@echo off
setlocal
cd /d "%~dp0"
echo === YT Downloader build (Windows) ===
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ was not found in PATH. Install it from python.org first.
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  python -m venv .venv || goto :fail
)
.venv\Scripts\python -m pip install --upgrade pip || goto :fail
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller || goto :fail
.venv\Scripts\python build.py || goto :fail
exit /b 0
:fail
echo.
echo BUILD FAILED.
exit /b 1
