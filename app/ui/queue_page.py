from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ..models import JobState
from .widgets import open_folder, scaled


class QueueItem(QFrame):
    cancel = Signal(object)
    retry = Signal(object)

    def __init__(self, job, thumbs):
        super().__init__()
        self.setObjectName("queueItem")
        self.job = job
        row = QHBoxLayout(self)
        self.thumb = QLabel()
        self.thumb.setFixedSize(96, 54)
        row.addWidget(self.thumb)
        col = QVBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("h2")
        self.status = QLabel()
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.details = QLabel()
        self.details.setObjectName("muted")
        for w in (self.title, self.status, self.bar, self.details):
            col.addWidget(w)
        row.addLayout(col, 1)
        btns = QVBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_retry = QPushButton("Retry")
        self.btn_open = QPushButton("Open folder")
        for b in (self.btn_cancel, self.btn_retry, self.btn_open):
            btns.addWidget(b)
        row.addLayout(btns)
        self.btn_cancel.clicked.connect(lambda: self.cancel.emit(self.job))
        self.btn_retry.clicked.connect(lambda: self.retry.emit(self.job))
        self.btn_open.clicked.connect(lambda: open_folder(self.job.result or self.job.spec.out_dir))
        thumbs.load(job.spec.entry.thumb_url, lambda pm: self.thumb.setPixmap(scaled(pm, 96, 54)))
        self.refresh()

    def refresh(self):
        j = self.job
        full = j.title
        self.title.setText(QFontMetrics(self.title.font()).elidedText(full, Qt.TextElideMode.ElideRight, 520))
        self.title.setToolTip(full)
        text = j.state.value
        color = {"Error": "#ff5c6c", "Completed": "#3ddc97"}.get(j.state.value)
        if j.state == JobState.ERROR:
            text += f" — {j.message}"
        elif j.state == JobState.COMPLETED and j.message:
            text += f" (warning: {j.message})"
        self.status.setText(f"<span style='color:{color}'>{text}</span>" if color else text)
        self.status.setToolTip(j.detail)
        self.bar.setValue(int(j.percent))
        parts = [p for p in (f"{j.percent:.0f}%" if j.state == JobState.DOWNLOADING else "",
                             j.speed, f"ETA {j.eta}" if j.eta else "", j.size) if p]
        self.details.setText("  ·  ".join(parts) if parts else (j.detail if j.state == JobState.ERROR else ""))
        active = not j.state.finished
        self.btn_cancel.setVisible(active)
        self.btn_retry.setVisible(j.state in (JobState.ERROR, JobState.CANCELLED))
        self.btn_open.setVisible(j.state == JobState.COMPLETED)


class QueuePage(QWidget):
    cancel = Signal(object)
    retry = Signal(object)
    clear = Signal()

    def __init__(self, thumbs):
        super().__init__()
        self.thumbs = thumbs
        self.items: dict[str, tuple[QListWidgetItem, QueueItem]] = {}
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        h = QLabel("Queue")
        h.setObjectName("h1")
        top.addWidget(h)
        top.addStretch()
        b = QPushButton("Clear finished")
        b.clicked.connect(self.clear)
        top.addWidget(b)
        lay.addLayout(top)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        lay.addWidget(self.list)
        self.empty = QLabel("The queue is empty.")
        self.empty.setObjectName("muted")
        lay.addWidget(self.empty)

    def add(self, job):
        it = QListWidgetItem(self.list)
        w = QueueItem(job, self.thumbs)
        w.cancel.connect(self.cancel)
        w.retry.connect(self.retry)
        it.setSizeHint(w.sizeHint())
        self.list.setItemWidget(it, w)
        self.items[job.id] = (it, w)
        self.empty.hide()

    def update_job(self, job):
        if job.id in self.items:
            it, w = self.items[job.id]
            w.refresh()
            it.setSizeHint(w.sizeHint())

    def remove(self, jobs):
        for j in jobs:
            if j.id in self.items:
                it, _ = self.items.pop(j.id)
                self.list.takeItem(self.list.row(it))
        self.empty.setVisible(not self.items)
