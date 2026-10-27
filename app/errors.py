"""Translate yt-dlp / ffmpeg output into friendly errors."""
from __future__ import annotations


class AppError(Exception):
    def __init__(self, code: str, message: str, detail: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


class Cancelled(Exception):
    pass


_COOKIE_HINT = ("Tip: Settings → Advanced → Custom arguments, e.g. "
                "--cookies-from-browser firefox")

# (code, message, keywords, hint) — order matters (first match wins)
_RULES = [
    ("PRIVATE", "Private video", ("private video",),
     "This video is private. " + _COOKIE_HINT),
    ("AGE", "Age restricted",
     ("confirm your age", "age-restricted", "age restricted", "inappropriate for some users"),
     "YouTube requires a signed-in account for this video. " + _COOKIE_HINT),
    ("BOT", "YouTube asks for verification",
     ("not a bot",), "YouTube blocked anonymous access. " + _COOKIE_HINT),
    ("INVALID_URL", "Invalid YouTube URL",
     ("unsupported url", "is not a valid url", "invalid url"),
     "Paste a youtube.com or youtu.be link."),
    ("FFMPEG", "FFmpeg not found",
     ("ffprobe and ffmpeg not found", "ffmpeg not found", "ffmpeg is not installed",
      "ffmpeg or avconv"),
     "Open Settings → Advanced and install/select FFmpeg."),
    ("UNAVAILABLE", "Video unavailable",
     ("video unavailable", "not available", "has been removed", "no longer available",
      "been terminated", "does not exist", "blocked it"),
     "The video was removed, is region-locked or is not available."),
    ("RATE", "Too many requests", ("http error 429", "too many requests"),
     "YouTube is rate limiting you. Wait a few minutes and retry."),
    ("NETWORK", "Network error",
     ("getaddrinfo", "timed out", "connection", "network is unreachable", "urlopen error",
      "unable to download webpage", "http error 5", "temporary failure", "ssl"),
     "Check your internet connection and retry."),
]


def classify(text: str) -> AppError:
    text = text or ""
    low = text.lower()
    errs = [ln.strip() for ln in text.splitlines() if ln.startswith("ERROR")]
    raw = errs[-1] if errs else text.strip()[-300:]
    for code, msg, keys, hint in _RULES:
        if any(k in low for k in keys):
            return AppError(code, msg, hint)
    return AppError("DOWNLOAD_FAILED", "Download failed", raw)
