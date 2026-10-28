"""Locate / install yt-dlp and FFmpeg (Windows, macOS, Linux)."""
from __future__ import annotations
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import APP_ID, VERSION, paths
from .errors import AppError

EXE = ".exe" if os.name == "nt" else ""
CNW = 0x08000000 if os.name == "nt" else 0
GH = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
FF_GH = "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/"
FF_MAC = "https://ffmpeg.martin-riedl.de/redirect/latest/macos/{arch}/release/{tool}.zip"
# where GUI apps on macOS / Linux do not look by default (Finder starts apps without the shell PATH)
EXTRA_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin", "/usr/bin", "/snap/bin",
              str(Path.home() / ".local" / "bin"))


def system() -> str:
    return platform.system()          # Windows | Darwin | Linux


def is_arm() -> bool:
    return platform.machine().lower() in ("arm64", "aarch64", "armv8l")


def ytdlp_asset(sysname: str | None = None, arm: bool | None = None) -> str:
    sysname = sysname or system()
    arm = is_arm() if arm is None else arm
    if sysname == "Windows":
        return "yt-dlp.exe"
    if sysname == "Darwin":
        return "yt-dlp_macos"           # universal binary (Intel + Apple Silicon)
    return "yt-dlp_linux_aarch64" if arm else "yt-dlp_linux"


def ffmpeg_urls(sysname: str | None = None, arm: bool | None = None) -> list[str]:
    sysname = sysname or system()
    arm = is_arm() if arm is None else arm
    if sysname == "Windows":
        return [FF_GH + "ffmpeg-master-latest-win64-gpl.zip"]
    if sysname == "Darwin":
        a = "arm64" if arm else "amd64"
        return [FF_MAC.format(arch=a, tool=t) for t in ("ffmpeg", "ffprobe")]
    return [FF_GH + f"ffmpeg-master-latest-{'linuxarm64' if arm else 'linux64'}-gpl.tar.xz"]


def tool_cmd(path) -> list[str]:
    """Command prefix for a tool. A .py file is run with Python (used by the tests)."""
    p = str(path)
    return [sys.executable, p] if p.endswith(".py") else [p]


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
    if w:
        return Path(w)
    if os.name != "nt":
        for d in EXTRA_DIRS:
            c = Path(d) / name
            if c.is_file() and os.access(c, os.X_OK):
                return c
    return None


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
    if system() == "Darwin" and paths.is_frozen():
        return paths.user_bin_dir()     # never write into the signed .app bundle
    d = paths.local_bin_dir()
    return d if writable(d) else paths.user_bin_dir()


def _make_executable(p: Path) -> None:
    if os.name != "nt":
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


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


def install_ytdlp(target: Path, progress=None) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    dest = target / ("yt-dlp" + EXE)
    tmp = target / (dest.name + ".part")
    _download(GH + ytdlp_asset(), tmp, progress, "yt-dlp")
    os.replace(tmp, dest)
    _make_executable(dest)
    return dest


def _extract(archive: Path, target: Path, wanted: set[str]) -> None:
    """Copy ffmpeg / ffprobe (any folder inside the archive) into target."""
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                base = os.path.basename(name)
                if base.lower() in wanted:
                    with z.open(name) as src, open(target / base, "wb") as out:
                        shutil.copyfileobj(src, out)
                    _make_executable(target / base)
        return
    with tarfile.open(archive) as t:
        for m in t.getmembers():
            base = os.path.basename(m.name)
            if m.isfile() and base in wanted:
                src = t.extractfile(m)
                with src, open(target / base, "wb") as out:
                    shutil.copyfileobj(src, out)
                _make_executable(target / base)


def install_ffmpeg(target: Path, progress=None) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    wanted = {"ffmpeg" + EXE, "ffprobe" + EXE}
    for i, url in enumerate(ffmpeg_urls()):
        part = target / f"ffmpeg-{i}{'.zip' if '.zip' in url else '.tar.xz'}.part"
        label = "FFprobe" if "ffprobe" in url else "FFmpeg"
        _download(url, part, progress, label)
        try:
            _extract(part, target, wanted)
        except (OSError, zipfile.BadZipFile, tarfile.TarError) as e:
            raise AppError("NETWORK", "FFmpeg could not be unpacked", str(e))
        finally:
            part.unlink(missing_ok=True)
    if not all((target / w).is_file() for w in wanted):
        raise AppError("FFMPEG", "FFmpeg install incomplete", f"ffmpeg/ffprobe not found in {target}")
    return target / ("ffmpeg" + EXE)


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
        p = subprocess.run(tool_cmd(path) + ["--version"], capture_output=True, text=True,
                           timeout=60, creationflags=CNW)
        return (p.stdout or p.stderr).strip().splitlines()[0]
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


def update_ytdlp(path: Path) -> str:
    p = subprocess.run(tool_cmd(path) + ["-U"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180, creationflags=CNW)
    return ((p.stdout or "") + (p.stderr or "")).strip()
