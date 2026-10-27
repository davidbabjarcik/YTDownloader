from __future__ import annotations
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel,
                               QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QHBoxLayout)

from .. import deps, naming
from ..errors import AppError
from .tasks import run_task


class NamingDialog(QDialog):
    """Asked before every download: choose / edit the file naming pattern."""
    CUSTOM = "Custom template…"

    def __init__(self, template: str, sample: dict, ext: str, ask_again: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("File name")
        self.setMinimumWidth(460)
        self.sample, self.ext = sample, ext
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("How should the file(s) be named?"))
        self.combo = QComboBox()
        for label, tpl in naming.PRESETS:
            self.combo.addItem(label, tpl)
        self.combo.addItem(self.CUSTOM, None)
        lay.addWidget(self.combo)
        self.edit = QLineEdit(template)
        self.edit.setPlaceholderText("{artist} - {title}")
        lay.addWidget(self.edit)
        hint = QLabel("Variables: " + "  ".join("{%s}" % v for v in naming.VARIABLES))
        hint.setObjectName("muted")
        lay.addWidget(hint)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)
        self.ask = QCheckBox("Always ask before downloading")
        self.ask.setChecked(ask_again)
        lay.addWidget(self.ask)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Download")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.combo.activated.connect(self._preset)
        self.edit.textChanged.connect(self._changed)
        self._changed(template)

    def _preset(self, i):
        tpl = self.combo.itemData(i)
        if tpl:
            self.edit.setText(tpl)

    def _changed(self, text):
        idx = next((i for i in range(self.combo.count() - 1) if self.combo.itemData(i) == text),
                   self.combo.count() - 1)
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        self.preview.setText(f"Preview: <b>{naming.render(text, self.sample)}.{self.ext}</b>")

    def template(self) -> str:
        return self.edit.text().strip() or "{title}"

    def ask_again(self) -> bool:
        return self.ask.isChecked()


class DepsDialog(QDialog):
    """Checks yt-dlp / FFmpeg and downloads whatever is missing."""
    def __init__(self, tools, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Components")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        missing = tools.missing()
        self.info = QLabel(
            ("Missing components: <b>%s</b>.<br>They can be downloaded automatically "
             "(about 150 MB, one time)." % ", ".join(missing)) if missing
            else "All components were found.")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.bar = QProgressBar()
        self.bar.hide()
        lay.addWidget(self.bar)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        self.go = QPushButton("Download now")
        self.go.setObjectName("primary")
        self.go.setVisible(bool(missing))
        self.close_btn = QPushButton("Close" if not missing else "Later")
        row.addStretch()
        row.addWidget(self.close_btn)
        row.addWidget(self.go)
        lay.addLayout(row)
        self.tools = tools
        self.go.clicked.connect(self._start)
        self.close_btn.clicked.connect(self.accept)

    def _start(self):
        self.go.setEnabled(False)
        self.bar.show()
        run_task(deps.install_missing, self.tools, with_progress=True,
                 on_progress=self._progress, on_done=self._done, on_fail=self._fail)

    def _progress(self, label, done, total):
        self.status.setText(f"Downloading {label}…")
        self.bar.setRange(0, 100 if total else 0)
        if total:
            self.bar.setValue(int(done / total * 100))

    def _done(self, target):
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.status.setText(f"Installed to {target}")
        self.info.setText("Done. You can close this window.")
        self.close_btn.setText("Close")

    def _fail(self, err):
        self.go.setEnabled(True)
        self.bar.hide()
        msg = err.message + (": " + err.detail if err.detail else "") if isinstance(err, AppError) else str(err)
        self.status.setText("<span style='color:#ff5c6c'>%s</span>" % msg)
