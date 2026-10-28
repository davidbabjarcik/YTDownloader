"""Build the desktop app for the current OS (PyInstaller).

  Windows -> dist/YTDownloader-<ver>-windows-x64.zip   YTDownloader.exe + bin/ (yt-dlp, FFmpeg included)
  macOS   -> dist/YTDownloader-<ver>-macos-<arch>.zip  YTDownloader.app (yt-dlp + FFmpeg download on first start)
  Linux   -> dist/YTDownloader-<ver>-linux-<arch>.tar.gz  folder with the YTDownloader program (same)

Usage:  pip install -r requirements.txt pyinstaller
        python build.py
"""
from __future__ import annotations
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from app import APP_ID, VERSION  # noqa: E402

SYSTEM = platform.system()
ARCH = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
    platform.machine().lower(), platform.machine().lower())
DIST, BUILD = ROOT / "dist", ROOT / "build"


def run(*cmd: str) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def pyinstaller(*extra: str) -> None:
    icon = ROOT / "assets" / ("icon.ico" if SYSTEM == "Windows" else "icon.icns")
    args = ["--noconfirm", "--clean", "--windowed", "--name", APP_ID]
    if icon.exists():
        args += ["--icon", str(icon)]
    run(sys.executable, "-m", "PyInstaller", *args, *extra, "main.py")


def main() -> int:
    shutil.rmtree(DIST, ignore_errors=True)
    shutil.rmtree(BUILD, ignore_errors=True)
    base = f"{APP_ID}-{VERSION}"

    if SYSTEM == "Windows":
        # one .exe + bin folder next to it: fast start, yt-dlp can update itself
        run(sys.executable, "tools/fetch_deps.py", "bin")
        pyinstaller("--onefile")
        (DIST / "bin").mkdir()
        for f in (ROOT / "bin").glob("*.exe"):
            shutil.copy2(f, DIST / "bin" / f.name)
        out = DIST / f"{base}-windows-{ARCH}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(DIST / f"{APP_ID}.exe", f"{APP_ID}.exe")
            for f in (DIST / "bin").iterdir():
                z.write(f, f"bin/{f.name}")
    elif SYSTEM == "Darwin":
        pyinstaller("--onedir", "--osx-bundle-identifier", "sk.daveeb.ytdownloader")
        app = DIST / f"{APP_ID}.app"
        out = DIST / f"{base}-macos-{ARCH}.zip"
        # ditto keeps the bundle's symlinks and signature intact (shutil would break them)
        run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(out))
    else:
        pyinstaller("--onedir")
        out = DIST / f"{base}-linux-{ARCH}.tar.gz"
        with tarfile.open(out, "w:gz") as t:
            t.add(DIST / APP_ID, arcname=APP_ID)
    print(f"\nDONE: {out}  ({out.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
