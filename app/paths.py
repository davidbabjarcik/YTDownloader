"""Filesystem locations (portable-friendly)."""
from __future__ import annotations
import os
import sys
from pathlib import Path

from . import APP_ID


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Folder with the .exe (frozen) or the project root (development)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Windows: %APPDATA%, macOS: ~/Library/Application Support, Linux: ~/.config (XDG)."""
    base = os.environ.get("YTDL_DATA_DIR") or os.environ.get("APPDATA")
    if not base:
        if sys.platform == "darwin":
            base = str(Path.home() / "Library" / "Application Support")
        else:
            base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    p = Path(base) / APP_ID
    p.mkdir(parents=True, exist_ok=True)
    return p


def local_bin_dir() -> Path:
    return app_dir() / "bin"


def user_bin_dir() -> Path:
    p = data_dir() / "bin"
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_file() -> Path:
    return data_dir() / "settings.json"


def archive_file() -> Path:
    return data_dir() / "history.jsonl"


def log_file() -> Path:
    return data_dir() / "app.log"


def default_music_dir() -> Path:
    m = Path.home() / "Music"
    return m if m.exists() else Path.home()
