"""Metadata detection + writing (ID3 / MP4 / FLAC) with embedded cover art."""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from pathlib import Path

NOISE = re.compile(
    r"\s*[\(\[]\s*(?:official\s*)?(?:music\s*)?"
    r"(?:video|audio|lyrics?(?:\s*video)?|visuali[sz]er|hd|hq|4k)\s*[\)\]]", re.I)
SPLIT = re.compile(r"^(.{1,80}?)\s+[-–—]\s+(.+)$")


@dataclass
class TrackMeta:
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    year: str = ""
    genre: str = ""
    id: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def detect_meta(info: dict, auto_detect: bool = True) -> TrackMeta:
    raw_title = (info.get("title") or "").strip()
    channel = re.sub(r"\s*-\s*Topic$", "", info.get("channel") or info.get("uploader") or "").strip()
    track = (info.get("track") or "").strip()
    artist = (info.get("artist") or ", ".join(info.get("artists") or []) or "").strip()
    if track and artist:
        title = track
    elif auto_detect:
        cleaned = NOISE.sub("", raw_title).strip()
        m = SPLIT.match(cleaned)
        if m:
            artist, title = m.group(1).strip(), m.group(2).strip()
        else:
            title = cleaned or raw_title
            artist = artist or channel
    else:
        title = track or raw_title
        artist = artist or channel
    year = str(info.get("release_year") or (info.get("release_date") or "")[:4]
               or (info.get("upload_date") or "")[:4] or "")
    genre = info.get("genre") or ""
    if isinstance(genre, list):
        genre = ", ".join(genre)
    return TrackMeta(title=title, artist=artist, album=info.get("album") or title,
                     album_artist=info.get("album_artist") or artist, year=year,
                     genre=genre, id=info.get("id") or "")


def write_tags(path: Path, meta: TrackMeta, cover: bytes | None, write_text: bool = True,
               comment: str = "") -> None:
    ext = path.suffix.lower()
    if ext == ".mp3":
        _mp3(path, meta, cover, write_text, comment)
    elif ext in (".m4a", ".mp4"):
        _mp4(path, meta, cover, write_text, comment)
    elif ext == ".flac":
        _flac(path, meta, cover, write_text, comment)


def _mp3(path, m, cover, write_text, comment=""):
    from mutagen.id3 import (ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TPE2, TDRC, TCON, APIC, COMM)
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    if write_text:
        tags.setall("TIT2", [TIT2(encoding=1, text=m.title)])
        tags.setall("TPE1", [TPE1(encoding=1, text=m.artist)])
        tags.setall("TALB", [TALB(encoding=1, text=m.album)])
        tags.setall("TPE2", [TPE2(encoding=1, text=m.album_artist)])
        if m.year:
            tags.setall("TDRC", [TDRC(encoding=1, text=m.year)])
        if m.genre:
            tags.setall("TCON", [TCON(encoding=1, text=m.genre)])
        if comment:
            tags.setall("COMM", [COMM(encoding=1, lang="eng", desc="", text=comment)])
    if cover:
        tags.delall("APIC")
        tags.add(APIC(encoding=1, mime="image/jpeg", type=3, desc="Cover", data=cover))
    tags.save(path, v2_version=3)


def _mp4(path, m, cover, write_text, comment=""):
    from mutagen.mp4 import MP4, MP4Cover
    f = MP4(path)
    if write_text:
        f["\xa9nam"] = [m.title]
        f["\xa9ART"] = [m.artist]
        f["\xa9alb"] = [m.album]
        f["aART"] = [m.album_artist]
        if m.year:
            f["\xa9day"] = [m.year]
        if m.genre:
            f["\xa9gen"] = [m.genre]
        if comment:
            f["\xa9cmt"] = [comment]
    if cover:
        f["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
    f.save()


def _flac(path, m, cover, write_text, comment=""):
    from mutagen.flac import FLAC, Picture
    f = FLAC(path)
    if write_text:
        f["title"], f["artist"], f["album"], f["albumartist"] = (
            [m.title], [m.artist], [m.album], [m.album_artist])
        if m.year:
            f["date"] = [m.year]
        if m.genre:
            f["genre"] = [m.genre]
        if comment:
            f["comment"] = [comment]
    if cover:
        pic = Picture()
        pic.type, pic.mime, pic.desc, pic.data = 3, "image/jpeg", "Cover", cover
        f.clear_pictures()
        f.add_picture(pic)
    f.save()
