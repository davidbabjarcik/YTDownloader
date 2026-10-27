from __future__ import annotations
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class ThumbLoader(QObject):
    """Async thumbnail loader with cache."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.nam = QNetworkAccessManager(self)
        self.cache: dict[str, QPixmap] = {}

    def load(self, url: str, callback) -> None:
        if not url:
            return
        if url in self.cache:
            callback(self.cache[url])
            return
        reply = self.nam.get(QNetworkRequest(QUrl(url)))
        reply.finished.connect(lambda r=reply: self._done(r, url, callback))

    def _done(self, reply: QNetworkReply, url: str, callback) -> None:
        data = reply.readAll()
        ok = reply.error() == QNetworkReply.NetworkError.NoError
        reply.deleteLater()
        pm = QPixmap()
        if ok and pm.loadFromData(bytes(data)):
            self.cache[url] = pm
            try:
                callback(pm)
            except RuntimeError:   # target widget already deleted
                pass


def scaled(pm: QPixmap, w: int, h: int) -> QPixmap:
    return pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                     Qt.TransformationMode.SmoothTransformation).copy(0, 0, w, h)


def open_folder(path) -> None:
    p = Path(path)
    if os.name == "nt" and p.is_file():
        subprocess.Popen(["explorer", "/select,", str(p)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p if p.is_dir() else p.parent)))
