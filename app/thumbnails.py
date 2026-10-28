"""Download thumbnails / artwork and turn them into cover art."""
from __future__ import annotations
import urllib.request
from io import BytesIO

CANDIDATES = ("maxresdefault", "sddefault", "hqdefault", "mqdefault")


def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_cover(video_id: str, fallback_url: str = "", youtube: bool = True) -> bytes | None:
    urls = [f"https://i.ytimg.com/vi/{video_id}/{q}.jpg" for q in CANDIDATES] if youtube else []
    if fallback_url:
        urls.append(fallback_url)
    for u in urls:
        try:
            data = _get(u)
            if len(data) > 2000:
                return data
        except Exception:  # noqa: BLE001
            continue
    return None


def prepare_cover(raw: bytes, square: bool = True, max_side: int = 1200) -> bytes:
    """Convert to JPEG (any source format), optionally centre-crop to 1:1."""
    from PIL import Image
    im = Image.open(BytesIO(raw)).convert("RGB")
    if square:
        w, h = im.size
        s = min(w, h)
        left, top = (w - s) // 2, (h - s) // 2
        im = im.crop((left, top, left + s, top + s))
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    buf = BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()
