"""Phone page: turn on web access and show the link + QR code for phones in the same Wi-Fi."""
from __future__ import annotations
from io import BytesIO

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)


def qr_pixmap(text: str, size: int = 240) -> QPixmap:
    import qrcode
    img = qrcode.make(text, border=2, box_size=10)
    buf = BytesIO()
    img.save(buf, "PNG")
    pm = QPixmap()
    pm.loadFromData(buf.getvalue(), "PNG")
    return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)


class PhonePage(QWidget):
    toggled = Signal(bool)          # turn web access on / off
    port_changed = Signal(int)
    new_code = Signal()

    def __init__(self, settings):
        super().__init__()
        lay = QVBoxLayout(self)
        h = QLabel("Phone")
        h.setObjectName("h1")
        lay.addWidget(h)
        intro = QLabel("Use this app from your phone: the phone must be in the <b>same Wi-Fi</b> as this computer. "
                       "Scan the QR code, paste a link on the phone and this computer downloads it. "
                       "Finished files can be saved to the phone too. On the phone, “Add to Home Screen” "
                       "puts it next to your apps.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        g = QGroupBox("Web access")
        f = QFormLayout(g)
        self.enable = QCheckBox("Allow phones in this network to use the app")
        self.enable.setChecked(settings.web_enabled)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(settings.web_port)
        self.port.setToolTip("Change it only if another program already uses this port.")
        f.addRow("", self.enable)
        f.addRow("Port", self.port)
        lay.addWidget(g)

        self.box = QGroupBox("Open on the phone")
        bl = QHBoxLayout(self.box)
        self.qr = QLabel()
        self.qr.setFixedSize(240, 240)
        self.qr.setStyleSheet("background:white; border-radius:8px;")
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self.qr)
        col = QVBoxLayout()
        self.link = QLabel()
        self.link.setWordWrap(True)
        self.link.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.others = QLabel()
        self.others.setObjectName("muted")
        self.others.setWordWrap(True)
        self.others.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        note = QLabel("The link contains an access code, so other people in the Wi-Fi cannot use the app. "
                      "“New access code” locks out phones that already have the old link. "
                      "If the phone cannot connect, allow the app in the computer's firewall.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        row = QHBoxLayout()
        self.copy = QPushButton("Copy link")
        self.regen = QPushButton("New access code")
        row.addWidget(self.copy)
        row.addWidget(self.regen)
        row.addStretch()
        for w in (self.link, self.others):
            col.addWidget(w)
        col.addLayout(row)
        col.addWidget(note)
        col.addStretch()
        bl.addLayout(col, 1)
        lay.addWidget(self.box)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch()

        self.enable.toggled.connect(self.toggled)
        self.port.editingFinished.connect(lambda: self.port_changed.emit(self.port.value()))
        self.regen.clicked.connect(self.new_code)
        self.copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._url))
        self._url = ""
        self.show_state([], "")

    def show_state(self, urls: list[str], error: str) -> None:
        self._url = urls[0] if urls else ""
        self.box.setVisible(bool(urls))
        if urls:
            self.qr.setPixmap(qr_pixmap(urls[0]))
            self.link.setText(f"<b>{urls[0]}</b>")
            self.others.setText("Other addresses of this computer: " + ", ".join(urls[1:]) if urls[1:] else "")
            self.others.setVisible(len(urls) > 1)
        if error:
            self.status.setText(f"<span style='color:#ff5c6c'>{error}</span>")
        else:
            self.status.setText("Running." if urls else "Web access is off.")
