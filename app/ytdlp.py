"""Thin wrapper around the yt-dlp executable (analysis + download command)."""
from __future__ import annotations
import json
import os
import re
import shlex
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import sources
from .deps import tool_cmd
from .errors import AppError, classify
from .models import AnalyzeResult, Entry

CNW = 0x08000000 if os.name == "nt" else 0
PROG = "[PROG]"
PROGRESS_TEMPLATE = ("download:[PROG]%(progress.status)s|%(progress.downloaded_bytes)s|"
                     "%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|"
                     "%(progress.speed)s|%(progress.eta)s")
STAGE_PREFIXES = ("[ExtractAudio]", "[Merger]", "[VideoConvertor]", "[VideoRemuxer]",
                  "[Fixup", "[ffmpeg]")
STD_BITRATES = (128, 160, 192, 224, 256, 320)
POSIX = os.name != "nt"
extract_urls = sources.extract_urls


def _custom_args(settings) -> list[str]:
    if not settings.custom_args.strip():
        return []
    try:
        return shlex.split(settings.custom_args)
    except ValueError:
        return settings.custom_args.split()


def _base(tools, settings, need_ffmpeg: bool) -> list[str]:
    if not tools.ytdlp:
        raise AppError("YTDLP_MISSING", "yt-dlp not found",
                       "Open Settings → Advanced and install yt-dlp.")
    cmd = tool_cmd(tools.ytdlp) + ["--ignore-config", "--encoding", "utf-8", "--no-colors",
           "--no-warnings"]
    if need_ffmpeg:
        if not (tools.ffmpeg and tools.ffprobe):
            raise AppError("FFMPEG", "FFmpeg not found",
                           "Open Settings → Advanced and install/select FFmpeg.")
        cmd += ["--ffmpeg-location", str(tools.ffmpeg.parent)]
    return cmd


def _capture(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, creationflags=CNW)
    except subprocess.TimeoutExpired:
        raise AppError("NETWORK", "Network error", "The request timed out.")
    except OSError as e:
        raise AppError("YTDLP_MISSING", "yt-dlp could not be started", str(e))


def fetch_info(url: str, tools, settings) -> dict:
    cmd = _base(tools, settings, False) + _custom_args(settings) + ["-J", "--no-playlist", url]
    p = _capture(cmd)
    if p.returncode != 0 or not p.stdout.strip():
        raise classify(p.stderr)
    return json.loads(p.stdout)


def search(query: str, n: int, tools, settings) -> list[dict]:
    """Flat search results (id, title, duration, channel) for 'ytsearchN:…' or a search URL."""
    cmd = _base(tools, settings, False) + _custom_args(settings) + [
        "-J", "--flat-playlist", "--playlist-end", str(n), query]
    p = _capture(cmd, timeout=90)
    if p.returncode != 0 or not p.stdout.strip():
        raise classify(p.stderr)
    return [e for e in json.loads(p.stdout).get("entries") or [] if e and e.get("id")]


def audio_summary(info: dict) -> tuple[float | None, str]:
    best = None
    for f in info.get("formats") or []:
        if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none"):
            if best is None or (f.get("abr") or 0) > (best.get("abr") or 0):
                best = f
    if not best:
        return None, ""
    return best.get("abr"), (best.get("acodec") or "").split(".")[0]


def video_heights(info: dict) -> list[int]:
    hs = {f["height"] for f in info.get("formats") or []
          if f.get("height") and f.get("vcodec") not in (None, "none")}
    return sorted(hs, reverse=True)


def _clean_channel(s: str) -> str:
    return re.sub(r"\s*-\s*Topic$", "", s or "").strip()


def _slug_title(url: str) -> str:
    """'https://soundcloud.com/artist/my-track-1' -> 'My track 1' (flat SoundCloud lists have no titles)."""
    m = re.search(r"soundcloud\.com/[^/]+/([^/?#]+)", url or "")
    if not m or m.group(1).isdigit():
        return ""
    t = m.group(1).replace("-", " ").strip()
    return t[:1].upper() + t[1:]


def _entry(d: dict, source: str = "youtube") -> Entry:
    vid = str(d.get("id") or "")
    extractor = d.get("ie_key") or d.get("extractor_key")
    if extractor:
        source = sources.from_extractor(extractor)
    if source == "youtube" and re.fullmatch(r"[\w-]{11}", vid):
        url = f"https://www.youtube.com/watch?v={vid}"
    else:
        url = d.get("webpage_url") or d.get("url") or ""
    thumb = d.get("thumbnail") or ""
    if not thumb and d.get("thumbnails"):
        thumb = (d["thumbnails"][-1] or {}).get("url") or ""
    meta = None
    if d.get("album"):
        meta = {"album": d.get("album") or "", "album_artist": d.get("album_artist") or ""}
    return Entry(id=vid, url=url, title=d.get("title") or _slug_title(url) or vid,
                 uploader=_clean_channel(d.get("channel") or d.get("uploader") or ""),
                 duration=int(d["duration"]) if d.get("duration") else None,
                 thumbnail=thumb, source=source, meta=meta)


def analyze_url(url: str, tools, settings) -> AnalyzeResult:
    source = sources.source_of(url)
    if source == "spotify":
        from . import spotify
        return spotify.analyze(url, settings)
    cmd = _base(tools, settings, False) + _custom_args(settings) + ["-J", "--flat-playlist", url]
    p = _capture(cmd)
    if p.returncode != 0 or not p.stdout.strip():
        raise classify(p.stderr)
    data = json.loads(p.stdout)
    if data.get("_type") == "playlist" or "entries" in data:
        entries = []
        for e in data.get("entries") or []:
            if not e or not e.get("id"):
                continue
            if (e.get("title") or "").startswith(("[Private video]", "[Deleted video]")):
                continue
            entries.append(_entry(e, source))
        if not entries:
            raise AppError("UNAVAILABLE", "Nothing to download", "The playlist has no playable items.")
        return AnalyzeResult(url, data.get("title") or "Playlist", True, entries)
    entry = _entry(data, source)
    entry.info = data
    abr, codec = audio_summary(data)
    return AnalyzeResult(url, entry.title, False, [entry], video_heights(data), abr, codec)


def analyze_many(urls: list[str], tools, settings) -> tuple[list[AnalyzeResult], list[AppError]]:
    results, errors = [], []
    for u in urls:
        try:
            results.append(analyze_url(u, tools, settings))
        except AppError as e:
            errors.append(e)
        except Exception as e:  # noqa: BLE001
            errors.append(classify(str(e)))
    return results, errors


def effective_bitrate(selected: int, source_abr: float | None, cap: bool) -> int:
    """Never pretend upscaling helps: optionally cap to the source quality."""
    if not cap or not source_abr:
        return selected
    for b in STD_BITRATES:
        if b >= source_abr:
            return min(selected, b)
    return selected


def build_download_cmd(tools, settings, spec, tmpdir: Path, source_abr, url: str = "") -> list[str]:
    cmd = _base(tools, settings, True) + [
        "--no-playlist", "--newline", "--no-mtime",
        "--progress-template", PROGRESS_TEMPLATE,
        "-o", str(tmpdir / "%(id)s.%(ext)s")]
    if spec.kind == "audio":
        if spec.fmt == "m4a":
            # prefer the native AAC stream: no re-encode, truly "best available" AAC
            cmd += ["-f", "bestaudio[ext=m4a]/bestaudio/best"]
        else:
            cmd += ["-f", "bestaudio/best"]
        cmd += ["-x", "--audio-format", spec.fmt]
        if spec.fmt == "mp3":
            kbps = effective_bitrate(int(spec.quality or 320), source_abr,
                                     settings.cap_bitrate_to_source)
            cmd += ["--audio-quality", f"{kbps}K"]
    else:
        if spec.quality == "best":
            sel = "bv*+ba/b"
        else:
            h = int(spec.quality)
            sel = f"bv*[height<={h}]+ba/b[height<={h}]"
        cmd += ["-f", sel, "-S", "res,ext:mp4:m4a", "--merge-output-format", "mp4"]
    cmd += _custom_args(settings)
    cmd.append(url or spec.entry.url)
    return cmd


@dataclass
class Progress:
    status: str
    downloaded: float | None
    total: float | None
    speed: float | None
    eta: float | None


def parse_progress(line: str) -> Progress | None:
    if not line.startswith(PROG):
        return None
    parts = (line[len(PROG):].strip().split("|") + ["NA"] * 6)[:6]

    def num(s: str):
        try:
            return float(s)
        except ValueError:
            return None
    status, down, total, est, speed, eta = parts
    return Progress(status, num(down), num(total) or num(est), num(speed), num(eta))


def kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, creationflags=CNW)
        else:   # yt-dlp runs in its own process group: kill it together with ffmpeg
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass


class ProcessRunner:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            kill_tree(self.proc)

    def run(self, cmd: list[str], on_line) -> tuple[int, list[str]]:
        lines: list[str] = []
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=CNW,
                start_new_session=POSIX)
        except OSError as e:
            raise AppError("YTDLP_MISSING", "yt-dlp could not be started", str(e))
        if self.cancelled:
            kill_tree(self.proc)
        for line in self.proc.stdout:
            line = line.rstrip("\r\n")
            lines.append(line)
            on_line(line)
        self.proc.stdout.close()
        return self.proc.wait(), lines
