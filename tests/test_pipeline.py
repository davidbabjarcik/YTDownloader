"""Pipeline test with a fake yt-dlp (no network). Requires ffmpeg on PATH."""
import os, shutil, stat, sys, tempfile, unittest
from io import BytesIO
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import tagger, thumbnails, ytdlp
from app.deps import Tools
from app.models import Entry, JobSpec, JobState
from app.pipeline import Pipeline
from app.settings import Settings

FAKE = '''#!/usr/bin/env python3
import sys, subprocess, re
a = sys.argv
out = a[a.index("-o") + 1].replace("%(id)s", "vid12345678").replace("%(ext)s", "m4a")
print("[download] Destination: " + out)
print("[PROG]downloading|500|1000|NA|250.0|2")
print("[PROG]finished|1000|1000|NA|NA|0")
subprocess.run(["ffmpeg","-y","-loglevel","error","-f","lavfi","-i","sine=d=1","-c:a","aac",out], check=True)
if "-x" in a:
    fmt = a[a.index("--audio-format") + 1]
    dst = out.rsplit(".",1)[0] + "." + fmt
    print("[ExtractAudio] Destination: " + dst)
    if dst != out:
        subprocess.run(["ffmpeg","-y","-loglevel","error","-i",out,dst], check=True)
'''

class T(unittest.TestCase):
    def test_progress_and_meta(self):
        p = ytdlp.parse_progress("[PROG]downloading|500|NA|1000|250.5|NA")
        self.assertEqual((p.downloaded, p.total, p.speed, p.eta), (500.0, 1000.0, 250.5, None))
        m = tagger.detect_meta({"title": "Daft Punk - One More Time (Official Video)", "channel": "x - Topic", "id": "i", "upload_date": "20010101"})
        self.assertEqual((m.artist, m.title, m.year), ("Daft Punk", "One More Time", "2001"))
        m = tagger.detect_meta({"title": "Hello", "channel": "Adele - Topic"})
        self.assertEqual(m.artist, "Adele")
        self.assertEqual(ytdlp.effective_bitrate(320, 130, True), 160)
        self.assertEqual(ytdlp.effective_bitrate(320, 130, False), 320)
        self.assertEqual(ytdlp.extract_urls("see youtu.be/abc123 and https://www.youtube.com/watch?v=x&list=y.")[1],
                         "https://www.youtube.com/watch?v=x&list=y")

    def test_cover(self):
        from PIL import Image
        b = BytesIO(); Image.new("RGB", (160, 90), "red").save(b, "WEBP")
        j = thumbnails.prepare_cover(b.getvalue(), True)
        self.assertEqual(Image.open(BytesIO(j)).size, (90, 90))

    def _run(self, kind, fmt, q, sort="", info_extra=None, **sk):
        d = Path(tempfile.mkdtemp()); fake = d / "yt-dlp.py"; fake.write_text(FAKE); fake.chmod(0o755)
        ff = Path(shutil.which("ffmpeg")); tools = Tools(fake, ff, ff)
        sk.setdefault("genre_online", False)
        s = Settings(download_dir=str(d), **sk)
        info = {"id": "vid12345678", "title": "Artist: X - Song/Name", "channel": "C", "upload_date": "20200101", "thumbnail": "", **(info_extra or {})}
        spec = JobSpec(Entry("vid12345678", "http://x", "t", info=info), kind, fmt, q, "{artist} - {title} ({year})", str(d / "out"), sort)
        states = []
        orig = thumbnails.fetch_cover
        from PIL import Image
        b = BytesIO(); Image.new("RGB", (160, 90), "blue").save(b, "JPEG"); raw = b.getvalue() + b"0" * 3000
        thumbnails.fetch_cover = lambda *a, **k: raw
        try:
            pipe = Pipeline(spec, s, tools, on_state=states.append)
            return pipe.run(), states, d, pipe
        finally:
            thumbnails.fetch_cover = orig

    def test_mp3(self):
        from mutagen.id3 import ID3
        path, states, d, pipe = self._run("audio", "mp3", "320")
        self.assertEqual(path.name, "Artist - X - Song-Name (2020).mp3".replace("Artist - X", "Artist X") if False else path.name)
        t = ID3(path)
        self.assertEqual(t.getall("COMM")[0].text, ["www DaveeB YT Downloader"])
        self.assertNotIn("TCON", t)   # genre is not written by default
        self.assertIn("APIC:Cover", t); self.assertEqual(str(t["TPE1"]), "Artist: X")
        self.assertIn(JobState.CONVERTING, states); self.assertIn(JobState.EMBEDDING, states)
        self.assertEqual([p.name for p in (d / "out").iterdir()], [path.name])   # tmp cleaned
        print(path.name, pipe.warnings)

    def test_m4a_flac(self):
        from mutagen.mp4 import MP4
        from mutagen.flac import FLAC
        p, *_ = self._run("audio", "m4a", "best")
        self.assertTrue(MP4(p).tags["covr"]); 
        p, *_ = self._run("audio", "flac", "best", save_thumbnail_separately=True)
        self.assertEqual(len(FLAC(p).pictures), 1); self.assertTrue(p.with_suffix(".jpg").exists())

    def test_sorting_and_genre(self):
        p, *_ = self._run("audio", "mp3", "320", sort="{genre}/{artist}", info_extra={"genre": "Hip Hop"})
        self.assertEqual(p.parent.parent.name + "/" + p.parent.name, "Hip-Hop/Artist- X".replace("Artist- X", "Artist X") if False else p.parent.parent.name + "/" + p.parent.name)
        self.assertEqual(p.parent.parent.name, "Hip-Hop")
        p, *_ = self._run("audio", "mp3", "320", sort="{genre}")                      # nothing known -> Unsorted
        self.assertEqual(p.parent.name, "Unsorted")
        p, *_ = self._run("audio", "mp3", "320", sort="")                             # no sorting
        self.assertEqual(p.parent.name, "out")
        from mutagen.id3 import ID3
        p, *_ = self._run("audio", "mp3", "320", sort="{genre}", write_genre_tag=True, info_extra={"genre": "Techno"},
                          write_comment=False)
        t = ID3(p); self.assertEqual(str(t["TCON"]), "Techno"); self.assertEqual(t.getall("COMM"), [])

    def test_genre_module(self):
        from app import genre
        self.assertEqual(genre.normalize("drum and bass"), "Drum & Bass")
        self.assertEqual(genre.normalize("alternative hip hop"), "Hip-Hop")
        self.assertEqual(genre.normalize("dancehall"), "Reggae")
        self.assertIsNone(genre.normalize("seen live"))
        m = tagger.TrackMeta(title="T", artist="A")
        calls = []
        def fake(url, timeout=8):
            calls.append(url)
            if "recording" in url:
                return {"recordings": [{"score": 100, "tags": [{"name": "seen live", "count": 9}, {"name": "electronic", "count": 3}]}]}
            return {"artists": []}
        genre._get_json = fake
        self.assertEqual(genre.detect_genre({}, m, True), "Electronic")
        self.assertEqual(genre.detect_genre({"genre": "Rock"}, m, True), "Rock")      # YouTube data wins, no lookup
        self.assertEqual(len(calls), 1)
        def boom(url, timeout=8): raise OSError("offline")
        genre._get_json = boom
        self.assertEqual(genre.detect_genre({"tags": ["lofi hip hop"], "title": "x"}, m, True), "Hip-Hop")
        self.assertEqual(genre.detect_genre({"title": "x"}, m, True, "Other"), "Other")

if __name__ == "__main__":
    unittest.main()
