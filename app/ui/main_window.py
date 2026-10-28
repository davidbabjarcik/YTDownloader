from __future__ import annotations
import dataclasses
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QRadioButton, QScrollArea,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, deps, naming, paths, sources, tagger, ytdlp
from ..archive import Archive
from ..errors import AppError, classify
from ..jobs import QueueManager
from ..models import JobSpec, JobState, fmt_duration
from .dialogs import DepsDialog, NamingDialog
from .queue_page import QueuePage
from .settings_page import SettingsPage
from .tasks import run_task
from .theme import apply_theme
from .widgets import ThumbLoader, open_folder, scaled

AUDIO_FORMATS = [("MP3", "mp3"), ("M4A (AAC)", "m4a"), ("FLAC", "flac")]
MP3_Q = [("Highest available (320 kbps)", "320"), ("256 kbps", "256"), ("192 kbps", "192")]
BEST_ONLY = {"m4a": [("Highest available (original AAC, no re-encode)", "best")],
             "flac": [("Lossless container (source is lossy)", "best")]}
DEFAULT_HEIGHTS = [2160, 1440, 1080, 720, 480, 360]
CUSTOM = "Custom template…"


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1040, 780)
        self.setAcceptDrops(True)
        self.settings = settings
        self.tools = deps.check(settings)
        self.thumbs = ThumbLoader(self)
        self.archive = Archive(paths.archive_file())
        self.queue = QueueManager(lambda: self.settings, self, self.archive)
        self.entries: list = []
        self.notes: list[str] = []
        self.heights = list(DEFAULT_HEIGHTS)
        self.single = False
        self._clip_urls: list[str] = []
        self._last_clip = ""
        self._last_out_dir = ""

        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.pages = QStackedWidget()
        lay.addWidget(self._build_sidebar())
        lay.addWidget(self.pages, 1)

        self.pages.addWidget(self._build_download_page())
        self.queue_page = QueuePage(self.thumbs)
        self.pages.addWidget(self._wrap(self.queue_page))
        self.settings_page = SettingsPage(settings, self.tools, self.archive)
        self.pages.addWidget(self.settings_page)

        self.queue.job_added.connect(self.queue_page.add)
        self.queue.job_added.connect(lambda j: self._update_nav())
        self.queue.job_changed.connect(self.queue_page.update_job)
        self.queue.job_changed.connect(lambda j: (self._update_summary(), self._update_nav()))
        self.queue.jobs_removed.connect(self.queue_page.remove)
        self.queue.jobs_removed.connect(lambda j: self._update_nav())
        self.queue.batch_finished.connect(self._on_batch_finished)
        self.queue_page.cancel.connect(self.queue.cancel)
        self.queue_page.retry.connect(lambda j: self.queue.retry(j, self.tools))
        self.queue_page.clear.connect(self.queue.clear_finished)
        self.settings_page.saved.connect(self._on_settings_saved)
        self.settings_page.install_requested.connect(lambda: self.check_dependencies(True))

        QGuiApplication.clipboard().dataChanged.connect(self._on_clipboard)
        self._refresh_formats()

    # ---------------------------------------------------------------- layout
    @staticmethod
    def _wrap(w: QWidget) -> QWidget:
        box = QWidget()
        l = QVBoxLayout(box)
        l.setContentsMargins(24, 20, 24, 20)
        l.addWidget(w)
        return box

    def _build_sidebar(self) -> QFrame:
        bar = QFrame(objectName="sidebar")
        bar.setFixedWidth(190)
        l = QVBoxLayout(bar)
        l.setContentsMargins(12, 18, 12, 12)
        t = QLabel(APP_NAME)
        t.setObjectName("h2")
        l.addWidget(t)
        l.addSpacing(14)
        self.nav_group = QButtonGroup(self)
        self.nav_btns = []
        for i, name in enumerate(("Download", "Queue", "Settings")):
            b = QPushButton(name)
            b.setObjectName("nav")
            b.setCheckable(True)
            self.nav_group.addButton(b, i)
            self.nav_btns.append(b)
            l.addWidget(b)
        self.nav_btns[0].setChecked(True)
        self.nav_group.idClicked.connect(self.pages.setCurrentIndex)
        l.addStretch()
        return bar

    def _build_download_page(self) -> QWidget:
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        h = QLabel("YT Downloader")
        h.setObjectName("h1")
        lay.addWidget(h)

        # clipboard banner
        self.banner = QFrame(objectName="banner")
        bl = QHBoxLayout(self.banner)
        self.banner_label = QLabel("Link detected – Analyze?")
        b1, b2 = QPushButton("Analyze"), QPushButton("Dismiss")
        b1.clicked.connect(self._banner_analyze)
        b2.clicked.connect(self.banner.hide)
        bl.addWidget(self.banner_label, 1)
        bl.addWidget(b1)
        bl.addWidget(b2)
        self.banner.hide()
        lay.addWidget(self.banner)

        lay.addWidget(QLabel("YouTube, SoundCloud or Spotify link – song or playlist "
                             "(one or more, one per line):"))
        self.url_edit = QPlainTextEdit(objectName="url")
        self.url_edit.setPlaceholderText("https://youtube.com/…   https://soundcloud.com/…   "
                                         "https://open.spotify.com/…\n(paste, or drag & drop a link here)")
        self.url_edit.setFixedHeight(88)
        lay.addWidget(self.url_edit)
        self.analyze_btn = QPushButton("ANALYZE")
        self.analyze_btn.setObjectName("primary")
        self.analyze_btn.clicked.connect(self._analyze)
        lay.addWidget(self.analyze_btn, 0, Qt.AlignmentFlag.AlignLeft)

        # error box
        self.error_box = QFrame(objectName="errorBox")
        el = QHBoxLayout(self.error_box)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        retry = QPushButton("Retry")
        retry.clicked.connect(self._analyze)
        el.addWidget(self.error_label, 1)
        el.addWidget(retry)
        self.error_box.hide()
        lay.addWidget(self.error_box)

        # preview stack: 0 empty, 1 single, 2 list
        self.preview = QStackedWidget()
        empty = QLabel("Paste a link and click ANALYZE.")
        empty.setObjectName("muted")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setMinimumHeight(120)
        self.preview.addWidget(empty)

        card = QFrame(objectName="card")
        cl = QHBoxLayout(card)
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(320, 180)
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.thumb_lbl)
        info = QVBoxLayout()
        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("h2")
        self.title_lbl.setWordWrap(True)
        self.artist_lbl = QLabel()
        self.dur_lbl = QLabel()
        self.src_lbl = QLabel()
        self.src_lbl.setObjectName("muted")
        self.src_lbl.setWordWrap(True)
        for w in (self.title_lbl, self.artist_lbl, self.dur_lbl, self.src_lbl):
            info.addWidget(w)
        info.addStretch()
        cl.addLayout(info, 1)
        self.preview.addWidget(card)

        lw = QWidget()
        ll = QVBoxLayout(lw)
        ll.setContentsMargins(0, 0, 0, 0)
        hr = QHBoxLayout()
        self.select_all = QCheckBox("Select all")
        self.list_info = QLabel()
        self.list_info.setObjectName("muted")
        hr.addWidget(self.select_all)
        hr.addStretch()
        hr.addWidget(self.list_info)
        ll.addLayout(hr)
        self.list_note = QLabel()
        self.list_note.setObjectName("muted")
        self.list_note.setWordWrap(True)
        self.list_note.hide()
        ll.addWidget(self.list_note)
        self.list = QListWidget()
        self.list.setIconSize(QSize(112, 63))
        self.list.setMinimumHeight(260)
        ll.addWidget(self.list)
        self.preview.addWidget(lw)
        self.select_all.clicked.connect(self._toggle_all)
        self.list.itemChanged.connect(self._list_changed)
        lay.addWidget(self.preview)

        # options
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.addWidget(QLabel("Download type:"), 0, 0)
        row = QHBoxLayout()
        self.rb_audio, self.rb_video = QRadioButton("Audio"), QRadioButton("Video")
        self.rb_audio.setChecked(True)
        row.addWidget(self.rb_audio)
        row.addWidget(self.rb_video)
        row.addStretch()
        grid.addLayout(row, 0, 1)
        self.fmt_combo, self.q_combo, self.name_combo = QComboBox(), QComboBox(), QComboBox()
        for label, tpl in naming.PRESETS:
            self.name_combo.addItem(label, tpl)
        self.name_combo.addItem(CUSTOM, None)
        self.custom_name = QLineEdit(self.settings.naming_template)
        self.custom_name.setPlaceholderText("{artist} - {title}")
        grid.addWidget(QLabel("Format:"), 1, 0)
        grid.addWidget(self.fmt_combo, 1, 1)
        grid.addWidget(QLabel("Quality:"), 2, 0)
        grid.addWidget(self.q_combo, 2, 1)
        grid.addWidget(QLabel("Filename:"), 3, 0)
        grid.addWidget(self.name_combo, 3, 1)
        grid.addWidget(self.custom_name, 4, 1)
        self.sort_combo = QComboBox()
        for label, tpl in naming.SORT_PRESETS:
            self.sort_combo.addItem(label, tpl)
        self.sort_combo.addItem(CUSTOM, None)
        self.custom_sort = QLineEdit(self.settings.sort_template)
        self.custom_sort.setPlaceholderText("{genre}/{artist}")
        self.custom_sort.setToolTip("Sub-folders inside the output folder. Variables: "
                                    "{genre} {artist} {album} {year}; use / for nested folders.")
        grid.addWidget(QLabel("Sort into folders:"), 5, 0)
        grid.addWidget(self.sort_combo, 5, 1)
        grid.addWidget(self.custom_sort, 6, 1)
        self.dir_edit = QLineEdit(self.settings.download_dir)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        grid.addWidget(QLabel("Output folder:"), 7, 0)
        dr = QHBoxLayout()
        dr.addWidget(self.dir_edit, 1)
        dr.addWidget(browse)
        grid.addLayout(dr, 7, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.rb_audio.toggled.connect(lambda _: (self._refresh_formats(), self._apply_history()))
        self.fmt_combo.currentIndexChanged.connect(lambda _: self._refresh_quality())
        self.name_combo.currentIndexChanged.connect(self._name_changed)
        self.sort_combo.currentIndexChanged.connect(self._sort_changed)

        self.download_btn = QPushButton("DOWNLOAD")
        self.download_btn.setObjectName("primary")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._download)
        lay.addWidget(self.download_btn, 0, Qt.AlignmentFlag.AlignLeft)

        # progress + result
        lay.addWidget(QLabel("Progress:"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        lay.addWidget(self.progress)
        self.status_lbl = QLabel("Idle")
        self.status_lbl.setObjectName("muted")
        lay.addWidget(self.status_lbl)
        self.done_box = QFrame(objectName="okBox")
        dl = QHBoxLayout(self.done_box)
        self.done_lbl = QLabel("Download completed")
        self.done_lbl.setObjectName("ok")
        ob = QPushButton("Open folder")
        ob.clicked.connect(lambda: open_folder(self._last_out_dir or self.dir_edit.text()))
        dl.addWidget(self.done_lbl, 1)
        dl.addWidget(ob)
        self.done_box.hide()
        lay.addWidget(self.done_box)
        lay.addStretch()

        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        return sa

    # ------------------------------------------------------- format widgets
    def _kind(self) -> str:
        return "audio" if self.rb_audio.isChecked() else "video"

    def _refresh_formats(self):
        self.fmt_combo.blockSignals(True)
        self.fmt_combo.clear()
        if self._kind() == "audio":
            for n, v in AUDIO_FORMATS:
                self.fmt_combo.addItem(n, v)
            self.fmt_combo.setCurrentIndex(max(0, self.fmt_combo.findData(self.settings.audio_format)))
        else:
            self.fmt_combo.addItem("MP4", "mp4")
        self.fmt_combo.blockSignals(False)
        self._refresh_quality()
        tpl = self.settings.naming_template
        i = next((k for k in range(self.name_combo.count() - 1)
                  if self.name_combo.itemData(k) == tpl), self.name_combo.count() - 1)
        self.name_combo.setCurrentIndex(i)
        self.custom_name.setText(tpl)
        self._name_changed()
        st = self.settings.sort_template
        k = next((i for i in range(self.sort_combo.count() - 1)
                  if self.sort_combo.itemData(i) == st), self.sort_combo.count() - 1)
        self.sort_combo.setCurrentIndex(k)
        self.custom_sort.setText(st)
        self._sort_changed()

    def _refresh_quality(self):
        fmt = self.fmt_combo.currentData()
        self.q_combo.clear()
        if self._kind() == "video":
            self.q_combo.addItem("Highest available", "best")
            for h in self.heights:
                self.q_combo.addItem(f"{h}p", str(h))
            want = self.settings.video_quality
        else:
            for n, v in (MP3_Q if fmt == "mp3" else BEST_ONLY.get(fmt, [])):
                self.q_combo.addItem(n, v)
            want = self.settings.audio_quality
        self.q_combo.setCurrentIndex(max(0, self.q_combo.findData(want)))

    def _name_changed(self, *_):
        custom = self.name_combo.currentData() is None
        self.custom_name.setVisible(custom)

    def _sort_changed(self, *_):
        self.custom_sort.setVisible(self.sort_combo.currentData() is None)

    def _sort_template(self) -> str:
        d = self.sort_combo.currentData()
        return self.custom_sort.text().strip() if d is None else d

    def _template(self) -> str:
        return (self.custom_name.text().strip() or "{title}") if self.name_combo.currentData() is None \
            else self.name_combo.currentData()

    def _browse(self):
        p = QFileDialog.getExistingDirectory(self, "Output folder", self.dir_edit.text())
        if p:
            self.dir_edit.setText(p)

    # ------------------------------------------------------------- analysis
    def _show_error(self, err: AppError):
        text = f"<b>{err.message}</b>" + (f"<br>{err.detail}" if err.detail else "")
        self.error_label.setText(text)
        self.error_box.show()

    def _analyze(self):
        urls = ytdlp.extract_urls(self.url_edit.toPlainText())
        if not urls:
            self._show_error(AppError("INVALID_URL", "Invalid link",
                                      "Paste a YouTube, SoundCloud or Spotify link."))
            return
        self.error_box.hide()
        self.banner.hide()
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("Analyzing…")
        run_task(ytdlp.analyze_many, urls, self.tools, self.settings,
                 on_done=self._on_analyzed, on_fail=self._on_analyze_failed)

    def _on_analyze_failed(self, e):
        self._reset_analyze_btn()
        self._show_error(e if isinstance(e, AppError) else classify(str(e)))

    def _reset_analyze_btn(self):
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("ANALYZE")

    def _on_analyzed(self, payload):
        results, errors = payload
        self._reset_analyze_btn()
        seen, entries = set(), []
        for r in results:
            for e in r.entries:
                if e.key not in seen:
                    seen.add(e.key)
                    entries.append(e)
        if errors:
            self._show_error(errors[0])
        if not entries:
            return
        self.entries = entries
        self.notes = [r.note for r in results if r.note]
        self.single = len(results) == 1 and not results[0].is_playlist and len(entries) == 1
        self.heights = (results[0].heights if self.single and results[0].heights else DEFAULT_HEIGHTS)
        has_yt = any(e.source == "youtube" for e in entries)
        if not has_yt:
            self.rb_audio.setChecked(True)
        self.rb_video.setEnabled(has_yt)
        self.rb_video.setToolTip("" if has_yt else "Video is only available for YouTube links.")
        if self.single:
            self._fill_single(entries[0], results[0])
        else:
            self._fill_list(entries, results)
        self._refresh_quality()
        self.download_btn.setEnabled(True)
        self.done_box.hide()

    def _fill_single(self, e, r):
        meta = tagger.detect_meta(e.info or {}, self.settings.auto_detect_artist)
        self.title_lbl.setText(f"Title: {meta.title or e.title}")
        self.artist_lbl.setText(f"Artist: {meta.artist or e.uploader or '—'}")
        self.dur_lbl.setText(f"Duration: {fmt_duration(e.duration)}   ·   {sources.LABELS.get(e.source, '')}")
        if e.source == "spotify":
            text = ("Spotify audio is protected, so the audio is taken from the best matching "
                    "YouTube upload. Title, artist, album and cover come from Spotify.")
        elif r.audio_abr:
            text = (f"Best audio source: {r.audio_codec or '?'} ≈ {r.audio_abr:.0f} kbps. "
                    "Re-encoding to a higher MP3 bitrate cannot improve this; the best source is used "
                    "and MP3 is capped at 320 kbps.")
        else:
            text = "Best available audio source will be used (MP3 capped at 320 kbps)."
        self.src_lbl.setText(text + "".join(f"<br>{n}" for n in self.notes) + self._history_text(e))
        self.thumb_lbl.clear()
        self.thumbs.load(e.big_thumb_url, lambda pm: self.thumb_lbl.setPixmap(scaled(pm, 320, 180)))
        self.preview.setCurrentIndex(1)

    def _history_text(self, e) -> str:
        r = self.archive.get(e.key, self._kind())
        return f"<br><b>Already downloaded</b> ({r['date']}): {r.get('path', '')}" if r else ""

    def _fill_list(self, entries, results):
        self.list.blockSignals(True)
        self.list.clear()
        for i, e in enumerate(entries):
            it = QListWidgetItem()
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setData(Qt.ItemDataRole.UserRole, i)
            it.setSizeHint(QSize(100, 72))
            self.list.addItem(it)
            self.thumbs.load(e.thumb_url, lambda pm, it=it: it.setIcon(QIcon(scaled(pm, 112, 63))))
        self.list.blockSignals(False)
        self.list_note.setText("<br>".join(self.notes))
        self.list_note.setVisible(bool(self.notes))
        self._apply_history()
        self.preview.setCurrentIndex(2)

    def _apply_history(self):
        """Label already downloaded items and (if enabled) leave them unchecked."""
        if not self.entries:
            return
        if self.single:
            text = self.src_lbl.text().split("<br><b>Already downloaded</b>")[0]
            self.src_lbl.setText(text + self._history_text(self.entries[0]))
            return
        if self.list.count() != len(self.entries):
            return
        kind = self._kind()
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            it = self.list.item(i)
            e = self.entries[it.data(Qt.ItemDataRole.UserRole)]
            r = self.archive.get(e.key, kind)
            mark = f"  •  ✓ downloaded {r['date']}" if r else ""
            it.setText(f"{e.title}\n{e.uploader or '—'}  •  {fmt_duration(e.duration)}{mark}")
            skip = bool(r) and self.settings.skip_downloaded
            it.setCheckState(Qt.CheckState.Unchecked if skip else Qt.CheckState.Checked)
        self.list.blockSignals(False)
        self._list_changed()

    def _toggle_all(self, checked: bool):
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.list.blockSignals(False)
        self._list_changed()

    def _list_changed(self, *_):
        n = sum(self.list.item(i).checkState() == Qt.CheckState.Checked for i in range(self.list.count()))
        kind = self._kind()
        done = 0 if self.single else sum(1 for e in self.entries if self.archive.has(e.key, kind))
        self.list_info.setText(f"{n} of {self.list.count()} selected"
                               + (f"  ·  {done} already downloaded" if done else ""))
        self.select_all.blockSignals(True)
        self.select_all.setChecked(n == self.list.count())
        self.select_all.blockSignals(False)

    def _selected(self) -> list:
        if self.single:
            return list(self.entries)
        return [self.entries[self.list.item(i).data(Qt.ItemDataRole.UserRole)]
                for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    # ------------------------------------------------------------- download
    def _download(self):
        sel = self._selected()
        if not sel:
            QMessageBox.information(self, APP_NAME, "Select at least one item.")
            return
        out_dir = self.dir_edit.text().strip()
        try:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Cannot use the output folder:\n{e}")
            return
        kind, fmt, quality = self._kind(), self.fmt_combo.currentData(), self.q_combo.currentData()
        if self.single and self.archive.has(sel[0].key, kind):
            r = self.archive.get(sel[0].key, kind)
            again = QMessageBox.question(self, APP_NAME, f"This was already downloaded on {r['date']}.\n"
                                         f"{r.get('path', '')}\n\nDownload it again?")
            if again != QMessageBox.StandardButton.Yes:
                return
        template = self._template()
        if self.settings.ask_naming:
            sample_info = sel[0].info or {"title": sel[0].title, "channel": sel[0].uploader, "id": sel[0].id}
            sample = tagger.apply_overrides(tagger.detect_meta(sample_info, self.settings.auto_detect_artist),
                                            sel[0].meta).as_dict()
            dlg = NamingDialog(template, sample, fmt, True, self)
            if dlg.exec() != NamingDialog.DialogCode.Accepted:
                return
            template = dlg.template()
            if not dlg.ask_again():
                self.settings.ask_naming = False
                self.settings.save()
        specs = [JobSpec(e, kind, fmt, quality, template, out_dir, self._sort_template()) for e in sel]
        self._last_out_dir = out_dir
        self.done_box.hide()
        self.progress.setValue(0)
        self.queue.enqueue(specs, dataclasses.replace(self.settings), self.tools)
        self.status_lbl.setText(f"Queued {len(specs)} item(s)…")

    def _update_summary(self):
        jobs = self.queue.batch
        if not jobs:
            return
        total = len(jobs)
        done = sum(j.state.finished for j in jobs)
        pct = sum(100 if j.state.finished else j.percent for j in jobs) / total
        self.progress.setValue(int(pct))
        active = [j for j in jobs if not j.state.finished and j.state != JobState.WAITING]
        if active:
            self.status_lbl.setText(f"{active[0].state.value}…  ({done}/{total} done)")
        elif done < total:
            self.status_lbl.setText(f"Waiting…  ({done}/{total} done)")

    def _on_batch_finished(self, jobs):
        ok = sum(j.state == JobState.COMPLETED for j in jobs)
        err = sum(j.state == JobState.ERROR for j in jobs)
        self.progress.setValue(100 if ok else self.progress.value())
        if err:
            self.status_lbl.setText(f"Finished: {ok} completed, {err} failed — see Queue (Retry).")
        else:
            self.status_lbl.setText("Finished.")
        self.settings_page._refresh_history()
        self._apply_history()
        if ok:
            self.done_lbl.setText("Download completed" if not err else f"Download completed ({ok} ok, {err} failed)")
            self.done_box.show()

    def _update_nav(self):
        n = sum(not j.state.finished for j in self.queue.jobs)
        self.nav_btns[1].setText(f"Queue ({n})" if n else "Queue")

    # --------------------------------------------------- clipboard / drops
    def _on_clipboard(self):
        if not self.settings.clipboard_watch:
            return
        text = QGuiApplication.clipboard().text().strip()
        if not text or text == self._last_clip:
            return
        urls = ytdlp.extract_urls(text)
        if urls and text != self.url_edit.toPlainText().strip():
            self._last_clip = text
            self._clip_urls = urls
            self.banner_label.setText("Link detected – Analyze?" if len(urls) == 1
                                      else f"{len(urls)} links detected – Analyze?")
            self.banner.show()

    def _banner_analyze(self):
        self.url_edit.setPlainText("\n".join(self._clip_urls))
        self.nav_btns[0].click()
        self._analyze()

    def dragEnterEvent(self, e):
        m = e.mimeData()
        if m.hasText() or m.hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        m = e.mimeData()
        text = m.text() or "\n".join(u.toString() for u in m.urls())
        urls = ytdlp.extract_urls(text)
        if not urls:
            self._show_error(AppError("INVALID_URL", "Invalid link",
                                      "That is not a YouTube, SoundCloud or Spotify link."))
            return
        cur = self.url_edit.toPlainText().strip()
        self.url_edit.setPlainText((cur + "\n" if cur else "") + "\n".join(urls))
        self.nav_btns[0].click()
        e.acceptProposedAction()

    # -------------------------------------------------------------- settings
    def _on_settings_saved(self, s):
        self.settings = s
        try:
            s.save()
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Could not save settings:\n{e}")
        apply_theme(QGuiApplication.instance(), s.theme)
        self.tools = deps.check(s)
        self.settings_page.refresh_tools(self.tools)
        self.dir_edit.setText(s.download_dir)
        self._refresh_formats()
        self.nav_btns[0].click()

    def check_dependencies(self, force: bool = False):
        self.tools = deps.check(self.settings)
        if force or not self.tools.complete:
            DepsDialog(self.tools, self).exec()
            self.tools = deps.check(self.settings)
            self.settings_page.refresh_tools(self.tools)
