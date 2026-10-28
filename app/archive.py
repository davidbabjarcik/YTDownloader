"""Download history: remembers what was already downloaded, so it can be skipped next time.

Stored as JSON lines in the app data folder. One record per item and type (audio / video):
{"key": "youtube:dQw4w9WgXcQ", "kind": "audio", "title": "...", "path": "...", "date": "2026-10-28"}
"""
from __future__ import annotations
import datetime as _dt
import json
import logging
import threading
from pathlib import Path


class Archive:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}
        self._load()

    @staticmethod
    def _id(key: str, kind: str) -> str:
        return f"{key}|{kind}"

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        self._items[self._id(r["key"], r.get("kind", "audio"))] = r
                    except (ValueError, KeyError):
                        continue
        except FileNotFoundError:
            pass
        except OSError:
            logging.exception("could not read the download history")

    def get(self, key: str, kind: str = "audio") -> dict | None:
        return self._items.get(self._id(key, kind))

    def has(self, key: str, kind: str = "audio") -> bool:
        return self._id(key, kind) in self._items

    def add(self, key: str, kind: str, title: str = "", path: str = "") -> None:
        r = {"key": key, "kind": kind, "title": title, "path": path,
             "date": _dt.date.today().isoformat()}
        with self._lock:
            self._items[self._id(key, kind)] = r
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            except OSError:
                logging.exception("could not write the download history")

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self.path.unlink(missing_ok=True)

    def __len__(self) -> int:
        return len(self._items)
