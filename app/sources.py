"""Supported link types: YouTube, SoundCloud, Spotify."""
from __future__ import annotations
import re

_PATTERNS = {
    "youtube": r"(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be|youtube-nocookie\.com)/[^\s<>\"']+",
    "soundcloud": r"(?:https?://)?(?:www\.|m\.|on\.)?soundcloud\.com/[^\s<>\"']+",
    "spotify": (r"(?:https?://)?open\.spotify\.com/(?:intl-[\w-]+/)?(?:track|album|playlist)/[A-Za-z0-9]+[^\s<>\"']*"
                r"|spotify:(?:track|album|playlist):[A-Za-z0-9]+"),
}
_ANY = re.compile("|".join(f"(?P<{k}>{v})" for k, v in _PATTERNS.items()), re.I)
LABELS = {"youtube": "YouTube", "soundcloud": "SoundCloud", "spotify": "Spotify"}


def extract_urls(text: str) -> list[str]:
    """All supported links in the text, in order, without duplicates."""
    urls: list[str] = []
    for m in _ANY.finditer(text or ""):
        u = m.group(0).rstrip(".,;)")
        if not u.lower().startswith(("http", "spotify:")):
            u = "https://" + u
        if u not in urls:
            urls.append(u)
    return urls


def source_of(url: str) -> str:
    m = _ANY.search(url or "")
    return m.lastgroup if m else "youtube"


def from_extractor(key: str) -> str:
    key = (key or "").lower()
    if key.startswith("soundcloud"):
        return "soundcloud"
    return "youtube"
