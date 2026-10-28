"""Web access from phones in the same network (no Qt here).

The desktop app runs this small HTTP server. A phone opens http://<pc-ip>:<port>/?t=<code>,
pastes a link, picks tracks and the PC downloads them. Finished files can be saved to the phone.

Every /api call needs the access code (?t=… or the X-Token header), so other people on the
same Wi-Fi cannot use it. The controller (the main window) does the real work.
"""
from __future__ import annotations
import hmac
import json
import logging
import mimetypes
import secrets
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import VERSION
from .errors import AppError

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC = {"/": "index.html", "/index.html": "index.html", "/manifest.webmanifest": "manifest.webmanifest",
          "/icon.svg": "icon.svg"}
MAX_BODY = 64 * 1024


def new_token() -> str:
    return secrets.token_urlsafe(6)


def lan_ips() -> list[str]:
    """IPv4 addresses other devices can use to reach this PC (best guess first)."""
    ips: list[str] = []
    try:   # the address of the interface that has the default route (no packet is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.0.1", 9))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


class Controller:
    """What the server needs from the app. The main window implements it."""
    def analyze(self, urls: list[str]):           # -> (list[AnalyzeResult], list[AppError])
        raise NotImplementedError

    def is_downloaded(self, key: str, kind: str) -> bool:
        return False

    def enqueue(self, entries, kind: str, fmt: str, quality: str) -> None:
        raise NotImplementedError

    def jobs(self) -> list:                       # Job objects (see jobs.py)
        return []

    def cancel(self, job_id: str) -> None: ...
    def retry(self, job_id: str) -> None: ...
    def clear(self) -> None: ...

    def defaults(self) -> dict:
        return {}


def job_dict(j) -> dict:
    res = getattr(j, "result", None)
    return {"id": j.id, "title": j.title, "state": j.state.value, "finished": j.state.finished,
            "percent": round(j.percent, 1), "speed": j.speed, "eta": j.eta, "size": j.size,
            "message": j.message, "detail": j.detail, "kind": j.spec.kind, "fmt": j.spec.fmt,
            "thumb": j.spec.entry.thumb_url, "file": res.name if res else "",
            "ok": j.state.value == "Completed" and bool(res)}


class _Handler(BaseHTTPRequestHandler):
    server_version = "YTDownloader/" + VERSION
    srv: "WebServer"

    def log_message(self, fmt, *args):  # keep the console quiet, use the app log
        logging.debug("web: " + fmt, *args)

    # ---------------------------------------------------------------- helpers
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, code: int, message: str, detail: str = "") -> None:
        self._json({"error": message, "detail": detail}, code)

    def _parts(self):
        u = urllib.parse.urlsplit(self.path)
        return u.path, urllib.parse.parse_qs(u.query)

    def _authorized(self, query) -> bool:
        given = self.headers.get("X-Token") or (query.get("t") or [""])[0]
        return bool(given) and hmac.compare_digest(given.encode(), self.srv.token.encode())

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("request too large")
        data = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        return data

    # ---------------------------------------------------------------- routes
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path, q = self._parts()
        if path in STATIC:
            f = WEB_DIR / STATIC[path]
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if f.suffix == ".webmanifest":
                ctype = "application/manifest+json"
            return self._send(200, f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))
        if not path.startswith("/api/"):
            return self._error(404, "Not found")
        if not self._authorized(q):
            return self._error(401, "Wrong access code", "Open the link or scan the QR code shown in the PC app.")
        c = self.srv.controller
        if path == "/api/state":
            return self._json({"version": VERSION, "defaults": c.defaults(),
                               "jobs": [job_dict(j) for j in list(c.jobs())]})
        if path.startswith("/api/file/"):
            return self._file(path.rsplit("/", 1)[1])
        return self._error(404, "Not found")

    def do_POST(self):
        path, q = self._parts()
        if not self._authorized(q):
            return self._error(401, "Wrong access code", "Open the link or scan the QR code shown in the PC app.")
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError) as e:
            return self._error(400, "Bad request", str(e))
        c, srv = self.srv.controller, self.srv
        try:
            if path == "/api/analyze":
                return self._json(srv.analyze(str(body.get("urls") or "")))
            if path == "/api/download":
                return self._json(srv.download(body))
            if path in ("/api/cancel", "/api/retry"):
                (c.cancel if path.endswith("cancel") else c.retry)(str(body.get("id") or ""))
                return self._json({"ok": True})
            if path == "/api/clear":
                c.clear()
                return self._json({"ok": True})
        except AppError as e:
            return self._error(400, e.message, e.detail)
        except Exception as e:  # noqa: BLE001 - never kill the server thread
            logging.exception("web request failed")
            return self._error(500, "Something went wrong", str(e))
        return self._error(404, "Not found")

    def _file(self, job_id: str) -> None:
        job = next((j for j in list(self.srv.controller.jobs()) if j.id == job_id), None)
        res = getattr(job, "result", None) if job else None
        if not res or not Path(res).is_file():
            return self._error(404, "File not found", "It is not finished yet or was moved.")
        p = Path(res)
        size = p.stat().st_size
        name = urllib.parse.quote(p.name)
        ascii_name = p.name.encode("ascii", "replace").decode().replace('"', "'").replace("?", "_")
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{name}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(p, "rb") as f:
            while chunk := f.read(256 * 1024):
                self.wfile.write(chunk)


class WebServer:
    def __init__(self, controller: Controller, token: str):
        self.controller = controller
        self.token = token
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self._analyses: dict[str, list] = {}
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self.httpd is not None

    @property
    def port(self) -> int:
        return self.httpd.server_address[1] if self.httpd else 0

    def start(self, port: int, host: str = "0.0.0.0") -> None:
        self.stop()
        handler = type("Handler", (_Handler,), {"srv": self})
        try:
            self.httpd = ThreadingHTTPServer((host, port), handler)
        except OSError as e:
            raise AppError("PORT", f"Port {port} is not available", str(e))
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="web", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    def urls(self) -> list[str]:
        return [f"http://{ip}:{self.port}/?t={self.token}" for ip in lan_ips()] if self.running else []

    # ---------------------------------------------------------------- actions
    def analyze(self, text: str) -> dict:
        from . import sources
        urls = sources.extract_urls(text)
        if not urls:
            raise AppError("INVALID_URL", "Invalid link", "Paste a YouTube, SoundCloud or Spotify link.")
        results, errors = self.controller.analyze(urls)
        seen, entries = set(), []
        for r in results:
            for e in r.entries:
                if e.key not in seen:
                    seen.add(e.key)
                    entries.append(e)
        aid = secrets.token_hex(6)
        with self._lock:
            self._analyses[aid] = entries
            while len(self._analyses) > 20:
                self._analyses.pop(next(iter(self._analyses)))
        c = self.controller
        return {
            "aid": aid,
            "title": results[0].title if len(results) == 1 else f"{len(entries)} items",
            "single": len(results) == 1 and not results[0].is_playlist and len(entries) == 1,
            "has_youtube": any(e.source == "youtube" for e in entries),
            "notes": [r.note for r in results if r.note],
            "errors": [{"error": e.message, "detail": e.detail} for e in errors],
            "items": [{"i": i, "title": e.title, "uploader": e.uploader, "duration": e.duration,
                       "source": e.source, "thumb": e.thumb_url,
                       "done": {"audio": c.is_downloaded(e.key, "audio"),
                                "video": c.is_downloaded(e.key, "video")}}
                      for i, e in enumerate(entries)],
        }

    def download(self, body: dict) -> dict:
        with self._lock:
            entries = self._analyses.get(str(body.get("aid") or ""))
        if entries is None:
            raise AppError("EXPIRED", "Analyze the link again", "The list is too old.")
        try:
            picked = [entries[int(i)] for i in body.get("items") or []]
        except (ValueError, IndexError, TypeError):
            raise AppError("BAD", "Bad selection")
        if not picked:
            raise AppError("EMPTY", "Select at least one item")
        kind = "video" if body.get("kind") == "video" else "audio"
        fmt = str(body.get("fmt") or ("mp4" if kind == "video" else "mp3"))
        if fmt not in (("mp4",) if kind == "video" else ("mp3", "m4a", "flac")):
            raise AppError("BAD", "Unsupported format", fmt)
        quality = str(body.get("quality") or ("best" if kind == "video" or fmt != "mp3" else "320"))
        if kind == "video" and any(e.source != "youtube" for e in picked):
            raise AppError("VIDEO_ONLY_YT", "Video is only available for YouTube")
        self.controller.enqueue(picked, kind, fmt, quality)
        return {"queued": len(picked)}
