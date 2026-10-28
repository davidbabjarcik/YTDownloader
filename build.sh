#!/usr/bin/env sh
# Build for macOS or Linux:  ./build.sh   (needs Python 3.10+)
set -e
cd "$(dirname "$0")"
echo "=== YT Downloader build ($(uname -s)) ==="
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt pyinstaller
.venv/bin/python build.py
