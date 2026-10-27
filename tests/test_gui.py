"""Offscreen smoke test of the GUI with a fake yt-dlp. Run: QT_QPA_PLATFORM=offscreen python tests/test_gui.py"""
import json, os, shutil, sys, tempfile, threading
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication
from app.settings import Settings
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme
from app.ui import tasks

FAKE = r'''#!/usr/bin/env python3
import sys, json, subprocess
a = sys.argv
if "-J" in a:
    if "--flat-playlist" in a and "list=PL" in a[-1]:
        print(json.dumps({"_type": "playlist", "title": "PL", "entries": [
            {"id": "aaaaaaaaaaa", "title": "A - One", "duration": 61, "channel": "X"},
            {"id": "bbbbbbbbbbb", "title": "[Private video]"},
            {"id": "ccccccccccc", "title": "C - Two", "duration": 5, "channel": "X"}]}))
    else:
        print(json.dumps({"id": "aaaaaaaaaaa", "title": "Art - Song (Official Video)", "channel": "Ch", "duration": 61,
            "upload_date": "20200101", "formats": [{"vcodec": "none", "acodec": "opus", "abr": 130},
            {"vcodec": "avc1", "acodec": "none", "height": 1080}, {"vcodec": "avc1", "acodec": "none", "height": 720}]}))
    sys.exit(0)
out = a[a.index("-o") + 1].replace("%(id)s", a[-1][-11:]).replace("%(ext)s", "m4a")
print("[download] Destination: " + out); print("[PROG]downloading|5|10|NA|2.0|1")
subprocess.run(["ffmpeg","-y","-loglevel","error","-f","lavfi","-i","sine=d=1",out], check=True)
fmt = a[a.index("--audio-format") + 1]; dst = out.rsplit(".",1)[0] + "." + fmt
print("[ExtractAudio] Destination: " + dst); subprocess.run(["ffmpeg","-y","-loglevel","error","-i",out,dst], check=True)
'''
d = Path(tempfile.mkdtemp()); fake = d / "yt-dlp"; fake.write_text(FAKE); fake.chmod(0o755)
s = Settings(download_dir=str(d / "out"), ask_naming=False, ytdlp_path=str(fake),
             ffmpeg_path=shutil.which("ffmpeg"), embed_thumbnail=False, genre_online=False)
app = QApplication([]); apply_theme(app, "dark")
w = MainWindow(s); w.show()
main_thread = threading.current_thread()
log = []
def step1():   # single video
    w.url_edit.setPlainText("https://youtu.be/aaaaaaaaaaa"); w._analyze()
def step2():
    assert w.single and w.download_btn.isEnabled(), "single analyze failed"
    assert [w.q_combo.itemData(i) for i in range(w.q_combo.count())][:3] == ["320", "256", "192"]
    assert "130" in w.src_lbl.text(), w.src_lbl.text()
    w.rb_video.setChecked(True)
    assert [w.q_combo.itemData(i) for i in range(w.q_combo.count())] == ["best", "1080", "720"]
    w.rb_audio.setChecked(True)
    w._download()
def step3():
    j = w.queue.jobs[0]; assert j.state.value == "Completed", (j.state, j.message, j.detail)
    assert j.result.name == "Art - Song.mp3" and j.result.parent.name == "Unsorted", j.result
    assert w.done_box.isVisible() or not w.done_box.isHidden()
    w.url_edit.setPlainText("https://www.youtube.com/playlist?list=PLxyz"); w._analyze()
def step4():
    assert not w.single and w.list.count() == 2, w.list.count()
    w.list.item(1).setCheckState(Qt.CheckState.Unchecked)
    assert [e.id for e in w._selected()] == ["aaaaaaaaaaa"]
    w.w2 = None
    w.url_edit.setPlainText("not a link"); w._analyze()
    assert not w.error_box.isHidden() and "Invalid" in w.error_label.text()
    print("GUI OK"); app.quit()
for i, (fn, t) in enumerate([(step1, 200), (step2, 2500), (step3, 6000), (step4, 8000)]):
    QTimer.singleShot(t, fn)
QTimer.singleShot(15000, lambda: (print("TIMEOUT"), app.exit(1)))
sys.exit(app.exec())
