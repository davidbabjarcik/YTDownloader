"""Genre detection: YouTube metadata -> MusicBrainz tags (optional) -> keywords in tags/title."""
from __future__ import annotations
import json
import logging
import re
import time
import urllib.parse
import urllib.request

from . import APP_ID, VERSION

# (canonical name, regex) — first match wins, so order matters
CANON = [
    ("Hip-Hop", r"hip[\s-]?hop|\brap\b|\btrap\b|drill|boom bap"),
    ("Drum & Bass", r"drum\s*(?:and|&|n)\s*bass|\bdnb\b|jungle|neurofunk"),
    ("Techno", r"techno"),
    ("House", r"\bhouse\b"),
    ("Trance", r"trance"),
    ("Dubstep", r"dubstep|brostep"),
    ("Reggae", r"reggae|dancehall|\bska\b"),
    ("Electronic", r"electro|\bedm\b|synth|\bdance\b|ambient|downtempo|future bass|hardstyle|idm"),
    ("Metal", r"metal|grindcore"),
    ("Punk", r"punk|hardcore"),
    ("Rock", r"rock|grunge|alternative|indie"),
    ("R&B / Soul", r"r\s?&\s?b|\brnb\b|soul|funk"),
    ("Jazz", r"jazz|bebop"),
    ("Blues", r"blues"),
    ("Classical", r"classical|orchestra|symphon|baroque"),
    ("Country", r"country|bluegrass"),
    ("Folk", r"folk|acoustic"),
    ("Latin", r"latin|reggaeton|salsa|bachata|cumbia"),
    ("Lo-Fi", r"lo-?fi"),
    ("Soundtrack", r"soundtrack|\bost\b|film score"),
    ("Pop", r"\bpop\b|k-?pop|j-?pop"),
]


def normalize(text: str) -> str | None:
    """Map a free-form genre/tag to one of the canonical genres (or None)."""
    for name, pat in CANON:
        if re.search(pat, text or "", re.I):
            return name
    return None


def _get_json(url: str, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": f"{APP_ID}/{VERSION} (personal use)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _best_tag(items: list[dict]) -> str:
    score: dict[str, int] = {}
    for it in items:
        for t in it.get("tags") or []:
            g = normalize(t.get("name", ""))
            if g:
                score[g] = score.get(g, 0) + int(t.get("count") or 1)
    return max(score, key=score.get) if score else ""


def musicbrainz_genre(artist: str, title: str) -> str:
    """Look the track (then the artist) up on MusicBrainz. Returns '' if unknown."""
    def q(s):
        return s.replace('"', " ").strip()
    base = "https://musicbrainz.org/ws/2/"
    try:
        if artist and title:
            query = f'recording:"{q(title)}" AND artist:"{q(artist)}"'
            data = _get_json(base + "recording/?fmt=json&limit=5&query=" + urllib.parse.quote(query))
            recs = [r for r in data.get("recordings", []) if int(r.get("score", 0)) >= 85]
            g = _best_tag(recs)
            if g:
                return g
            time.sleep(1.1)           # MusicBrainz asks for max. 1 request / second
        if artist:
            query = f'artist:"{q(artist.split(",")[0])}"'
            data = _get_json(base + "artist/?fmt=json&limit=1&query=" + urllib.parse.quote(query))
            arts = [a for a in data.get("artists", []) if int(a.get("score", 0)) >= 90]
            return _best_tag(arts)
    except Exception as e:  # noqa: BLE001 - offline / rate limited: just fall through
        logging.info("MusicBrainz lookup failed: %s", e)
    return ""


def keywords_genre(info: dict) -> str:
    parts = list(info.get("tags") or []) + list(info.get("categories") or [])
    parts.append(info.get("title") or "")
    return normalize(" | ".join(parts)) or ""


def detect_genre(info: dict, meta, online: bool = True, unknown: str = "Unsorted") -> str:
    g = info.get("genre") or info.get("genres") or ""
    if isinstance(g, list):
        g = g[0] if g else ""
    g = str(g).strip()
    if g:
        return normalize(g) or g
    if online:
        g = musicbrainz_genre(meta.artist, meta.title)
        if g:
            return g
    return keywords_genre(info) or unknown
