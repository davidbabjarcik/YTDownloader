from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class JobState(str, Enum):
    WAITING = "Waiting"
    SEARCHING = "Searching on YouTube"
    DOWNLOADING = "Downloading"
    CONVERTING = "Converting"
    EMBEDDING = "Embedding metadata"
    COMPLETED = "Completed"
    ERROR = "Error"
    CANCELLED = "Cancelled"

    @property
    def finished(self) -> bool:
        return self in (JobState.COMPLETED, JobState.ERROR, JobState.CANCELLED)


@dataclass
class Entry:
    """One downloadable item (a single video/track or a playlist item)."""
    id: str
    url: str
    title: str
    uploader: str = ""
    duration: int | None = None
    thumbnail: str = ""
    info: dict | None = None            # full yt-dlp info (single videos only)
    source: str = "youtube"             # youtube | soundcloud | spotify
    meta: dict | None = None            # known tags that win over detection (Spotify, SoundCloud sets)
    cover_url: str = ""                 # square cover art (Spotify)

    @property
    def is_youtube_id(self) -> bool:
        return self.source == "youtube" and len(self.id) == 11

    @property
    def thumb_url(self) -> str:
        if self.is_youtube_id:
            return f"https://i.ytimg.com/vi/{self.id}/mqdefault.jpg"
        return self.thumbnail or self.cover_url

    @property
    def big_thumb_url(self) -> str:
        if self.is_youtube_id:
            return f"https://i.ytimg.com/vi/{self.id}/hqdefault.jpg"
        return self.cover_url or self.thumbnail

    @property
    def key(self) -> str:
        """Identity in the download history, e.g. 'spotify:4cOdK2wGLETKBW3PvgPWqT'."""
        return f"{self.source}:{self.id}"


@dataclass
class AnalyzeResult:
    source_url: str
    title: str
    is_playlist: bool
    entries: list[Entry]
    heights: list[int] = field(default_factory=list)
    audio_abr: float | None = None
    audio_codec: str = ""
    note: str = ""                      # shown above the list (e.g. Spotify 100-track limit)


@dataclass
class JobSpec:
    entry: Entry
    kind: str          # "audio" | "video"
    fmt: str           # mp3 | m4a | flac | mp4
    quality: str       # "320" | "best" | "1080" ...
    template: str
    out_dir: str
    sort_template: str = ""


def fmt_duration(sec) -> str:
    if not sec:
        return "—"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_size(n) -> str:
    if not n:
        return ""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def fmt_speed(bps) -> str:
    return f"{fmt_size(bps)}/s" if bps else ""


def fmt_eta(sec) -> str:
    if sec is None:
        return ""
    return fmt_duration(sec) if sec else "0:00"
