"""Spotify links (track / album / playlist).

Spotify audio is DRM protected, so it is never downloaded from Spotify. The app reads the
track list and tags from Spotify, finds the same song on YouTube (YouTube Music first) and
downloads that audio. Tags and cover art come from Spotify.

Without API keys the public embed page is used: no login, but playlists show max. 100 tracks.
With your own Client ID + Secret (Settings → Spotify) the Web API loads whole playlists.
"""
from __future__ import annotations
import base64
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .errors import AppError
from .models import AnalyzeResult, Entry

SP_RE = re.compile(r"(?:open\.spotify\.com/(?:intl-[\w-]+/)?|spotify:)(track|album|playlist)[/:]([A-Za-z0-9]+)", re.I)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
EMBED_LIMIT = 100
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', re.S)
# words that usually mean "not the studio version" (penalised unless the Spotify title has them too)
VARIANTS = ("live", "cover", "remix", "karaoke", "instrumental", "sped up", "slowed", "nightcore",
            "8d", "reverb", "acoustic", "extended", "bass boosted", "reaction", "tutorial")


def parse(url: str) -> tuple[str, str]:
    m = SP_RE.search(url or "")
    if not m:
        raise AppError("INVALID_URL", "Invalid Spotify link",
                       "Use a Spotify track, album or playlist link.")
    return m.group(1).lower(), m.group(2)


def _get(url: str, headers: dict | None = None, data: bytes | None = None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Language": "en",
                                                         **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _artists(value) -> str:
    if isinstance(value, list):
        names = [a.get("name", "") if isinstance(a, dict) else str(a) for a in value]
    else:
        names = re.split(r",", str(value or ""))
    return ", ".join(n.replace("\xa0", " ").strip() for n in names if n and n.strip())


def _best_image(images) -> str:
    imgs = [i for i in images or [] if isinstance(i, dict) and i.get("url")]
    if not imgs:
        return ""
    return max(imgs, key=lambda i: (i.get("width") or i.get("maxWidth") or 0))["url"]


def _year(date) -> str:
    if isinstance(date, dict):
        date = date.get("isoString") or ""
    m = re.match(r"(\d{4})", str(date or ""))
    return m.group(1) if m else ""


def _entry(tid: str, title: str, artists: str, duration_ms, album: str = "", album_artist: str = "",
           year: str = "", cover: str = "", number=None) -> Entry:
    meta = {"title": title, "artist": artists, "album": album, "album_artist": album_artist,
            "year": year, "track": f"{int(number):02d}" if number else ""}
    return Entry(id=tid, url=f"https://open.spotify.com/track/{tid}", title=title, uploader=artists,
                 duration=int(duration_ms / 1000) if duration_ms else None, thumbnail=cover,
                 source="spotify", meta=meta, cover_url=cover)


# ------------------------------------------------------------------ embed (no keys)
def embed(kind: str, sid: str) -> dict:
    try:
        html = _get(f"https://open.spotify.com/embed/{kind}/{sid}").decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise AppError("UNAVAILABLE", "Not found on Spotify",
                           "The link is private, removed or not available in your country.")
        raise AppError("NETWORK", "Spotify is not reachable", str(e))
    except OSError as e:
        raise AppError("NETWORK", "Spotify is not reachable", str(e))
    m = NEXT_DATA.search(html)
    try:
        return json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (AttributeError, KeyError, TypeError, ValueError):
        raise AppError("SPOTIFY", "Spotify page could not be read",
                       "Spotify may have changed its page. Add API keys in Settings → Spotify.")


def _from_embed(kind: str, sid: str, url: str) -> AnalyzeResult:
    ent = embed(kind, sid)
    cover = _best_image((ent.get("visualIdentity") or {}).get("image")) or \
        _best_image((ent.get("coverArt") or {}).get("sources"))
    name = ent.get("name") or ent.get("title") or ""
    if kind == "track":
        e = _entry(sid, name, _artists(ent.get("artists")), ent.get("duration"),
                   year=_year(ent.get("releaseDate")), cover=cover)
        return AnalyzeResult(url, name, False, [e])
    entries = []
    for i, t in enumerate(ent.get("trackList") or []):
        uri = t.get("uri") or ""
        if not uri.startswith("spotify:track:") or t.get("isPlayable") is False:
            continue
        tid = uri.rsplit(":", 1)[1]
        if kind == "album":
            entries.append(_entry(tid, t.get("title", ""), _artists(t.get("subtitle")), t.get("duration"),
                                  album=name, album_artist=_artists(ent.get("subtitle")), cover=cover,
                                  number=i + 1))
        else:   # playlist: per-track cover / year are filled in just before the download
            entries.append(_entry(tid, t.get("title", ""), _artists(t.get("subtitle")), t.get("duration")))
    if not entries:
        raise AppError("UNAVAILABLE", "Nothing to download", "The Spotify list has no playable tracks.")
    note = ""
    if kind == "playlist" and len(ent.get("trackList") or []) >= EMBED_LIMIT:
        note = (f"Spotify shows only the first {EMBED_LIMIT} tracks without login. Add a Spotify "
                "Client ID + Secret in Settings → Spotify to load the whole playlist.")
    return AnalyzeResult(url, name, True, entries, note=note)


# ------------------------------------------------------------------ Web API (own keys)
_token: dict = {}


def _api_token(cid: str, secret: str) -> str:
    if _token.get("id") == cid and _token.get("exp", 0) > time.time() + 60:
        return _token["value"]
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    try:
        data = json.loads(_get("https://accounts.spotify.com/api/token",
                               {"Authorization": f"Basic {auth}",
                                "Content-Type": "application/x-www-form-urlencoded"},
                               b"grant_type=client_credentials"))
    except urllib.error.HTTPError as e:
        raise AppError("SPOTIFY", "Spotify login failed",
                       f"Check the Client ID and Secret in Settings → Spotify (HTTP {e.code}).")
    _token.update(id=cid, value=data["access_token"], exp=time.time() + int(data.get("expires_in", 3600)))
    return _token["value"]


def _api(path: str, token: str) -> dict:
    url = path if path.startswith("http") else "https://api.spotify.com/v1/" + path
    try:
        return json.loads(_get(url, {"Authorization": f"Bearer {token}"}))
    except urllib.error.HTTPError as e:
        raise AppError("SPOTIFY", "Spotify API error", f"HTTP {e.code} for {path}")


def _api_track(t: dict, album: dict | None = None) -> Entry | None:
    if not t or not t.get("id") or t.get("type", "track") != "track":
        return None
    al = album or t.get("album") or {}
    return _entry(t["id"], t.get("name", ""), _artists(t.get("artists")), t.get("duration_ms"),
                  album=al.get("name", ""), album_artist=_artists(al.get("artists")),
                  year=_year(al.get("release_date")), cover=_best_image(al.get("images")),
                  number=t.get("track_number") if album or al else None)


def _from_api(kind: str, sid: str, url: str, token: str) -> AnalyzeResult:
    if kind == "track":
        e = _api_track(_api(f"tracks/{sid}", token))
        return AnalyzeResult(url, e.title, False, [e])
    if kind == "album":
        al = _api(f"albums/{sid}", token)
        page, items = al.get("tracks") or {}, []
        while page:
            items += page.get("items") or []
            page = _api(page["next"], token) if page.get("next") else None
        entries = [e for e in (_api_track(t, al) for t in items) if e]
        return AnalyzeResult(url, al.get("name", "Album"), True, entries)
    pl = _api(f"playlists/{sid}?fields=name", token)
    page, entries = _api(f"playlists/{sid}/tracks?limit=100", token), []
    while page:
        for it in page.get("items") or []:
            e = _api_track((it or {}).get("track"))
            if e:
                if e.meta:
                    e.meta["track"] = ""     # album track numbers make no sense inside a playlist
                entries.append(e)
        page = _api(page["next"], token) if page.get("next") else None
    if not entries:
        raise AppError("UNAVAILABLE", "Nothing to download", "The Spotify playlist has no playable tracks.")
    return AnalyzeResult(url, pl.get("name", "Playlist"), True, entries)


# ------------------------------------------------------------------ public API
def has_keys(settings) -> bool:
    return bool(getattr(settings, "spotify_client_id", "") and getattr(settings, "spotify_client_secret", ""))


def analyze(url: str, settings) -> AnalyzeResult:
    kind, sid = parse(url)
    if has_keys(settings):
        try:
            return _from_api(kind, sid, url, _api_token(settings.spotify_client_id,
                                                        settings.spotify_client_secret))
        except AppError as e:
            logging.warning("Spotify API failed (%s), using the public page", e.detail)
            r = _from_embed(kind, sid, url)
            r.note = f"{e.message}: {e.detail} Showing public data instead."
            return r
    return _from_embed(kind, sid, url)


def enrich(entry: Entry) -> None:
    """Fill a missing cover / year from the track's public page (playlist items)."""
    if entry.cover_url and (entry.meta or {}).get("year"):
        return
    try:
        ent = embed("track", entry.id)
    except AppError as e:
        logging.info("Spotify enrich failed: %s", e.detail)
        return
    cover = _best_image((ent.get("visualIdentity") or {}).get("image"))
    if cover and not entry.cover_url:
        entry.cover_url = cover
    meta = entry.meta if entry.meta is not None else {}
    if not meta.get("year"):
        meta["year"] = _year(ent.get("releaseDate"))
    entry.meta = meta


# ------------------------------------------------------------------ YouTube matching
def _words(s: str) -> set[str]:
    return set(re.findall(r"\w+", (s or "").lower()))


def score(cand_title: str, cand_channel: str, cand_dur, title: str, artist: str, dur) -> float | None:
    """Higher = better. None = duration too different to be the same recording."""
    diff = 0.0
    if cand_dur and dur:
        diff = abs(float(cand_dur) - float(dur))
        if diff > max(10.0, dur * 0.08):
            return None
    text = f"{cand_title} {cand_channel}"
    cw, tw, aw = _words(text), _words(title), _words(artist)
    s = 3 * len(tw & cw) / max(1, len(tw)) + 2 * len(aw & cw) / max(1, len(aw))
    low, want = cand_title.lower(), title.lower()
    s -= sum(2 for v in VARIANTS if re.search(rf"\b{v}\b", low) and v not in want)
    return s - diff / 10


def _watch(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def match(entry: Entry, tools, settings) -> dict:
    """Find the YouTube upload for a Spotify track; returns its full yt-dlp info."""
    from . import ytdlp
    meta = entry.meta or {}
    title, artist, dur = meta.get("title") or entry.title, meta.get("artist") or entry.uploader, entry.duration
    query = f"{artist.split(',')[0]} {title}".strip()

    # 1) YouTube Music "songs" (official audio, usually the exact recording)
    try:
        url = "https://music.youtube.com/search?q=" + urllib.parse.quote(query) + "#songs"
        for c in ytdlp.search(url, 3, tools, settings)[:2]:
            info = ytdlp.fetch_info(_watch(c["id"]), tools, settings)
            sc = score(info.get("track") or info.get("title") or "",
                       info.get("artist") or info.get("channel") or "", info.get("duration"), title, artist, dur)
            if sc is not None and sc >= 2.0:
                return info
    except AppError as e:
        logging.info("YouTube Music search failed: %s", e.detail)

    # 2) normal YouTube search, best score wins
    cands = ytdlp.search(f"ytsearch8:{query}", 8, tools, settings)
    ranked = sorted(((score(c.get("title") or "", c.get("channel") or c.get("uploader") or "",
                            c.get("duration"), title, artist, dur), c) for c in cands),
                    key=lambda x: -999 if x[0] is None else x[0], reverse=True)
    for sc, c in ranked:
        if sc is not None and sc >= 1.5:
            return ytdlp.fetch_info(_watch(c["id"]), tools, settings)
    raise AppError("NO_MATCH", "Not found on YouTube",
                   f"No YouTube upload matches “{artist} - {title}”.")
