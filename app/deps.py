"""Locate / install yt-dlp and FFmpeg."""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import APP_ID, VERSION, paths
from .errors import AppError

EXE = ".exe" if os.name == "nt" else ""
CNW = 0x08000000 if os.name == "nt" else 0
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
FFMPEG_ZIP_URL = ("https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/"
                  "ffmpeg-master-latest-win64-gpl.zip")


@dataclass
class Tools:
    ytdlp: Path | None = None
    ffmpeg: Path | None = None
    ffprobe: Path | None = None

    @property
    def complete(self) -> bool:
        return bool(self.ytdlp and self.ffmpeg and self.ffprobe)

    def missing(self) -> list[str]:
        return [n for n, v in (("yt-dlp", self.ytdlp), ("ffmpeg", self.ffmpeg),
                               ("ffprobe", self.ffprobe)) if not v]


def _custom(name: str, custom: str) -> Path | None:
    if not custom:
        return None
    p = Path(custom)
    if p.is_dir():
        p = p / (name + EXE)
    return p if p.is_file() else None


def find_tool(name: str, custom: str = "") -> Path | None:
    p = _custom(name, custom)
    if p:
        return p
    for d in (paths.local_bin_dir(), paths.user_bin_dir()):
        c = d / (name + EXE)
        if c.is_file():
            return c
    w = shutil.which(name)
    return Path(w) if w else None


def check(settings) -> Tools:
    ffmpeg = find_tool("ffmpeg", settings.ffmpeg_path)
    ffprobe = None
    if ffmpeg:
        sib = ffmpeg.parent / ("ffprobe" + EXE)
        ffprobe = sib if sib.is_file() else find_tool("ffprobe")
    return Tools(find_tool("yt-dlp", settings.ytdlp_path), ffmpeg, ffprobe)


def writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=d):
            pass
        return True
    except OSError:
        return False


def install_dir() -> Path:
    d = paths.local_bin_dir()
    return d if writable(d) else paths.user_bin_dir()


def _download(url: str, dest: Path, progress=None, label: str = "") -> None:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_ID}/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(label, float(done), float(total))
    except OSError as e:
        raise AppError("NETWORK", "Network error", f"Could not download {label}: {e}")


def _need_windows():
    if os.name != "nt":
        raise AppError("UNSUPPORTED", "Automatic install works on Windows only",
                       "Install yt-dlp and ffmpeg with your package manager.")


def install_ytdlp(target: Path, progress=None) -> Path:
    _need_windows()
    target.mkdir(parents=True, exist_ok=True)
    tmp = target / "yt-dlp.exe.part"
    _download(YTDLP_URL, tmp, progress, "yt-dlp")
    dest = target / "yt-dlp.exe"
    os.replace(tmp, dest)
    return dest


def install_ffmpeg(target: Path, progress=None) -> Path:
    _need_windows()
    target.mkdir(parents=True, exist_ok=True)
    zpath = target / "ffmpeg.zip.part"
    _download(FFMPEG_ZIP_URL, zpath, progress, "FFmpeg")
    try:
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                base = os.path.basename(name).lower()
                if base in ("ffmpeg.exe", "ffprobe.exe"):
                    with z.open(name) as src, open(target / base, "wb") as out:
                        shutil.copyfileobj(src, out)
    finally:
        zpath.unlink(missing_ok=True)
    return target / "ffmpeg.exe"


def install_missing(tools: Tools, progress=None) -> Path:
    target = install_dir()
    if not tools.ytdlp:
        install_ytdlp(target, progress)
    if not (tools.ffmpeg and tools.ffprobe):
        install_ffmpeg(target, progress)
    return target


def tool_version(path: Path | None) -> str:
    if not path:
        return "not found"
    try:
        p = subprocess.run([str(path), "--version"], capture_output=True, text=True,
                           timeout=60, creationflags=CNW)
        return (p.stdout or p.stderr).strip().splitlines()[0]
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


def update_ytdlp(path: Path) -> str:
    p = subprocess.run([str(path), "-U"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180, creationflags=CNW)
    return ((p.stdout or "") + (p.stderr or "")).strip()
