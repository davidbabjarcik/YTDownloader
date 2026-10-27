"""File name templates: {title} {artist} {album} {year} {id}."""
from __future__ import annotations
import re
from pathlib import Path

VARIABLES = ("title", "artist", "album", "year", "genre", "id")
PRESETS = [
    ("Artist - Title", "{artist} - {title}"),
    ("Title", "{title}"),
    ("Artist - Title (Year)", "{artist} - {title} ({year})"),
    ("Artist - Title [YouTube]", "{artist} - {title} [YouTube]"),
]
SORT_PRESETS = [
    ("No folders", ""),
    ("Genre", "{genre}"),
    ("Genre / Artist", "{genre}/{artist}"),
    ("Artist", "{artist}"),
    ("Artist / Album", "{artist}/{album}"),
    ("Year", "{year}"),
    ("Genre / Year", "{genre}/{year}"),
]
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def sanitize(name: str) -> str:
    """Make text safe for Windows file names (\\ / : * ? " < > | are replaced/removed)."""
    name = re.sub(r"[\\/|]", "-", name)
    name = name.replace(":", " -").replace('"', "'")
    name = re.sub(r"[*?<>]", "", name)
    name = re.sub(r"[\x00-\x1f]", "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name[:150].strip(" .")


def _render(template: str, meta: dict) -> str:
    values = {k: str(meta.get(k) or "") for k in VARIABLES}
    text = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), ""), template)
    text = sanitize(text)
    # tidy up pieces left empty by missing metadata
    text = re.sub(r"\(\s*\)|\[\s*\]", "", text)
    text = re.sub(r"(\s[-–—]\s*){2,}", " - ", text)
    text = re.sub(r"^[\s\-–—_.]+|[\s\-–—_.]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    return sanitize(text)


def render(template: str, meta: dict) -> str:
    return (_render(template or "{title}", meta)
            or sanitize(str(meta.get("id") or "")) or "download")


def render_folders(template: str, meta: dict) -> list[str]:
    """'{genre}/{artist}' -> ['Hip-Hop', 'Artist']; parts that end up empty are skipped."""
    parts = []
    for part in re.split(r"[\\/]+", template or ""):
        if part.strip():
            r = _render(part, meta)
            if r:
                parts.append(r)
    return parts


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    p = folder / f"{stem}.{ext}"
    n = 1
    while p.exists():
        p = folder / f"{stem} ({n}).{ext}"
        n += 1
    return p
