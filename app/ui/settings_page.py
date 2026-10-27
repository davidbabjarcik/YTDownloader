from __future__ import annotations
import dataclasses

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import deps, naming
from .tasks import run_task


def _path_row(edit: QLineEdit, pick_dir=False, filt="Executables (*.exe);;All files (*)"):
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    btn = QPushButton("Browse")
    row.addWidget(edit, 1)
    row.addWidget(btn)

    def pick():
        p = (QFileDialog.getExistingDirectory(box, "Select folder", edit.text()) if pick_dir
             else QFileDialog.getOpenFileName(box, "Select file", edit.text(), filt)[0])
        if p:
            edit.setText(p)
    btn.clicked.connect(pick)
    return box


class SettingsPage(QScrollArea):
    saved = Signal(object)
    install_requested = Signal()

    def __init__(self, settings, tools):
        super().__init__()
        self.setWidgetResizable(True)
        self.s = settings
        body = QWidget()
        self.setWidget(body)
        lay = QVBoxLayout(body)
        h = QLabel("Settings")
        h.setObjectName("h1")
        lay.addWidget(h)

        # Downloads
        g = QGroupBox("Downloads")
        f = QFormLayout(g)
        self.dir = QLineEdit(settings.download_dir)
        f.addRow("Default download folder", _path_row(self.dir, True))
        self.afmt = QComboBox()
        for n, v in (("MP3", "mp3"), ("M4A (AAC)", "m4a"), ("FLAC", "flac")):
            self.afmt.addItem(n, v)
        self.aq = QComboBox()
        for n, v in (("Highest available (320 kbps)", "320"), ("256 kbps", "256"), ("192 kbps", "192")):
            self.aq.addItem(n, v)
        self.vq = QComboBox()
        for n, v in (("Highest available", "best"), ("1080p", "1080"), ("720p", "720"),
                     ("480p", "480"), ("360p", "360")):
            self.vq.addItem(n, v)
        self.tpl = QLineEdit(settings.naming_template)
        self.tpl.setToolTip("Variables: " + " ".join("{%s}" % v for v in naming.VARIABLES))
        self.ask = QCheckBox("Ask for the file name pattern before each download")
        f.addRow("Default audio format", self.afmt)
        f.addRow("Default MP3 quality", self.aq)
        f.addRow("Default video quality", self.vq)
        f.addRow("Naming template", self.tpl)
        f.addRow("", self.ask)
        lay.addWidget(g)

        # Metadata
        g = QGroupBox("Metadata")
        v = QVBoxLayout(g)
        self.embed = QCheckBox("Embed thumbnail into audio")
        self.id3 = QCheckBox("Write ID3 / tag metadata")
        self.sep = QCheckBox("Save thumbnail separately (.jpg)")
        self.auto = QCheckBox("Automatically detect artist/title")
        self.crop = QCheckBox("Crop cover art to a square")
        self.cap = QCheckBox("Never encode MP3 above the source quality (e.g. 128 kbps source → 160 kbps)")
        for w in (self.embed, self.id3, self.sep, self.auto, self.crop, self.cap):
            v.addWidget(w)
        lay.addWidget(g)

        # Appearance
        g = QGroupBox("Appearance")
        f = QFormLayout(g)
        self.theme = QComboBox()
        for n, val in (("Dark mode", "dark"), ("Light mode", "light"), ("System theme", "system")):
            self.theme.addItem(n, val)
        self.clip = QCheckBox("Offer to analyze YouTube URLs copied to the clipboard")
        f.addRow("Theme", self.theme)
        f.addRow("", self.clip)
        lay.addWidget(g)

        # Organization & tags
        g = QGroupBox("Organization & tags")
        f = QFormLayout(g)
        self.sort = QLineEdit(settings.sort_template)
        self.sort.setPlaceholderText("empty = no folders, e.g. {genre}/{artist}")
        self.sort.setToolTip("Default folder structure inside the output folder. Variables: "
                             "{genre} {artist} {album} {year}; use / for nested folders.")
        self.unk = QLineEdit(settings.unknown_genre)
        self.gonline = QCheckBox("Look up the genre online (MusicBrainz) when YouTube does not provide it")
        self.wgenre = QCheckBox("Also write the genre into the tag")
        self.wcomment = QCheckBox("Write a comment into every tag:")
        self.comment = QLineEdit(settings.tag_comment)
        f.addRow("Default sorting", self.sort)
        f.addRow("Folder for unknown genre", self.unk)
        f.addRow("", self.gonline)
        f.addRow("", self.wgenre)
        f.addRow("", self.wcomment)
        f.addRow("Comment text", self.comment)
        lay.addWidget(g)

        # Advanced
        g = QGroupBox("Advanced")
        f = QFormLayout(g)
        self.ytdlp = QLineEdit(settings.ytdlp_path)
        self.ytdlp.setPlaceholderText("Auto (bin folder / PATH)")
        self.ytver = QLabel("…")
        self.ytver.setObjectName("muted")
        upd = QPushButton("Update yt-dlp")
        upd.clicked.connect(self._update)
        self.ffmpeg = QLineEdit(settings.ffmpeg_path)
        self.ffmpeg.setPlaceholderText("Auto (bin folder / PATH)")
        self.ffstate = QLabel("")
        self.ffstate.setObjectName("muted")
        inst = QPushButton("Check / install components")
        inst.clicked.connect(self.install_requested)
        self.par = QSpinBox()
        self.par.setRange(1, 8)
        self.args = QLineEdit(settings.custom_args)
        self.args.setPlaceholderText("e.g. --cookies-from-browser firefox")
        f.addRow("yt-dlp executable", _path_row(self.ytdlp))
        row = QHBoxLayout()
        row.addWidget(self.ytver, 1)
        row.addWidget(upd)
        f.addRow("yt-dlp version", row)
        f.addRow("FFmpeg executable", _path_row(self.ffmpeg))
        row = QHBoxLayout()
        row.addWidget(self.ffstate, 1)
        row.addWidget(inst)
        f.addRow("Components", row)
        f.addRow("Max simultaneous downloads", self.par)
        f.addRow("Custom yt-dlp arguments", self.args)
        lay.addWidget(g)

        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        lay.addWidget(save)
        lay.addStretch()
        self.load(settings)
        self.refresh_tools(tools)

    def load(self, s):
        self.dir.setText(s.download_dir)
        for combo, val in ((self.afmt, s.audio_format), (self.aq, s.audio_quality),
                           (self.vq, s.video_quality), (self.theme, s.theme)):
            combo.setCurrentIndex(max(0, combo.findData(val)))
        self.tpl.setText(s.naming_template)
        self.ask.setChecked(s.ask_naming)
        self.embed.setChecked(s.embed_thumbnail)
        self.id3.setChecked(s.write_id3)
        self.sep.setChecked(s.save_thumbnail_separately)
        self.auto.setChecked(s.auto_detect_artist)
        self.crop.setChecked(s.crop_cover_square)
        self.cap.setChecked(s.cap_bitrate_to_source)
        self.clip.setChecked(s.clipboard_watch)
        self.par.setValue(s.max_parallel)
        self.sort.setText(s.sort_template)
        self.unk.setText(s.unknown_genre)
        self.gonline.setChecked(s.genre_online)
        self.wgenre.setChecked(s.write_genre_tag)
        self.wcomment.setChecked(s.write_comment)
        self.comment.setText(s.tag_comment)

    def collect(self):
        return dataclasses.replace(
            self.s, download_dir=self.dir.text().strip() or self.s.download_dir,
            audio_format=self.afmt.currentData(), audio_quality=self.aq.currentData(),
            video_quality=self.vq.currentData(),
            naming_template=self.tpl.text().strip() or "{artist} - {title}",
            ask_naming=self.ask.isChecked(), embed_thumbnail=self.embed.isChecked(),
            write_id3=self.id3.isChecked(), save_thumbnail_separately=self.sep.isChecked(),
            auto_detect_artist=self.auto.isChecked(), crop_cover_square=self.crop.isChecked(),
            cap_bitrate_to_source=self.cap.isChecked(), theme=self.theme.currentData(),
            clipboard_watch=self.clip.isChecked(), ytdlp_path=self.ytdlp.text().strip(),
            ffmpeg_path=self.ffmpeg.text().strip(), max_parallel=self.par.value(),
            custom_args=self.args.text().strip(), sort_template=self.sort.text().strip(),
            unknown_genre=self.unk.text().strip() or "Unsorted", genre_online=self.gonline.isChecked(),
            write_genre_tag=self.wgenre.isChecked(), write_comment=self.wcomment.isChecked(),
            tag_comment=self.comment.text().strip())

    def _save(self):
        self.s = self.collect()
        self.saved.emit(self.s)

    def refresh_tools(self, tools):
        self.tools = tools
        self.ffstate.setText("all found" if tools.complete else "missing: " + ", ".join(tools.missing()))
        self.ytver.setText("checking…")
        run_task(deps.tool_version, tools.ytdlp, on_done=self.ytver.setText)

    def _update(self):
        if not self.tools.ytdlp:
            QMessageBox.warning(self, "yt-dlp", "yt-dlp was not found. Use “Check / install components”.")
            return
        self.ytver.setText("updating…")

        def done(out):
            self.ytver.setText("…")
            QMessageBox.information(self, "yt-dlp", out or "Done.")
            self.refresh_tools(self.tools)
        run_task(deps.update_ytdlp, self.tools.ytdlp, on_done=done,
                 on_fail=lambda e: (self.ytver.setText("update failed"),
                                    QMessageBox.warning(self, "yt-dlp", str(e))))
