"""SoundCloud / Spotify / history / installers. No network: Spotify pages and yt-dlp are faked.
Pipeline part requires ffmpeg on PATH."""
import io, json, os, shutil, sys, tarfile, tempfile, unittest, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import deps, sources, spotify, tagger, thumbnails, ytdlp
from app.archive import Archive
from app.deps import Tools
from app.models import JobSpec, JobState
from app.pipeline import Pipeline
from app.settings import Settings


def embed_html(entity):
    data = {"props": {"pageProps": {"state": {"data": {"entity": entity}}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'.encode()


TRACK = {"name": "Never Gonna Give You Up", "artists": [{"name": "Rick Astley"}], "duration": 213573,
         "releaseDate": {"isoString": "1987-11-12T00:00:00Z"},
         "visualIdentity": {"image": [{"url": "https://img/small", "maxWidth": 64},
                                      {"url": "https://img/big", "maxWidth": 640}]}}
ALBUM = {"name": "Global Warming", "subtitle": "Pitbull", "visualIdentity": {"image": [{"url": "https://img/al", "maxWidth": 300}]},
         "trackList": [{"uri": "spotify:track:aaa", "title": "Global Warming (feat. Sensato)", "subtitle": "Pitbull,\xa0Sensato", "duration": 85400},
                       {"uri": "spotify:track:bbb", "title": "Don't Stop the Party", "subtitle": "Pitbull", "duration": 206000}]}
PLAYLIST = {"name": "Big list", "trackList": [{"uri": f"spotify:track:t{i}", "title": f"Song {i}", "subtitle": "X", "duration": 1000}
                                              for i in range(100)]}


class Sources(unittest.TestCase):
    def test_extract(self):
        text = ("a https://soundcloud.com/forss/flickermood, b https://on.soundcloud.com/abc "
                "c open.spotify.com/intl-sk/track/4cOdK2wGLETKBW3PvgPWqT?si=1 d spotify:album:xyz "
                "e youtu.be/abc12345678 f https://example.com/x")
        urls = sources.extract_urls(text)
        self.assertEqual([sources.source_of(u) for u in urls],
                         ["soundcloud", "soundcloud", "spotify", "spotify", "youtube"])
        self.assertTrue(urls[2].startswith("https://open.spotify.com/intl-sk/track/"))
        self.assertEqual(spotify.parse(urls[2]), ("track", "4cOdK2wGLETKBW3PvgPWqT"))
        self.assertEqual(spotify.parse("spotify:album:xyz"), ("album", "xyz"))

    def test_soundcloud_flat_entry(self):
        e = ytdlp._entry({"ie_key": "Soundcloud", "id": "75206121", "_type": "url_transparent",
                          "url": "https://soundcloud.com/the-concept-band/world-on-fire-1",
                          "album": "The Royal Concept EP", "album_artist": "The Royal Concept"}, "soundcloud")
        self.assertEqual((e.source, e.title, e.key), ("soundcloud", "World on fire 1", "soundcloud:75206121"))
        self.assertEqual(e.meta["album"], "The Royal Concept EP")
        self.assertEqual(e.thumb_url, "")
        y = ytdlp._entry({"id": "dQw4w9WgXcQ", "title": "x"})
        self.assertTrue(y.thumb_url.startswith("https://i.ytimg.com/vi/dQw4w9WgXcQ"))


class Spotify(unittest.TestCase):
    def setUp(self):
        self.pages = {"track": TRACK, "album": ALBUM, "playlist": PLAYLIST}
        self.orig = spotify._get
        spotify._get = lambda url, *a, **k: embed_html(self.pages[url.split("/embed/")[1].split("/")[0]])

    def tearDown(self):
        spotify._get = self.orig

    def test_track(self):
        r = spotify.analyze("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT", Settings())
        e = r.entries[0]
        self.assertFalse(r.is_playlist)
        self.assertEqual((e.title, e.uploader, e.duration, e.cover_url, e.meta["year"]),
                         ("Never Gonna Give You Up", "Rick Astley", 213, "https://img/big", "1987"))
        self.assertEqual(e.key, "spotify:4cOdK2wGLETKBW3PvgPWqT")

    def test_album_and_playlist(self):
        r = spotify.analyze("https://open.spotify.com/album/4aawyAB9vmqN3uQ7FjRGTy", Settings())
        a, b = r.entries
        self.assertEqual((a.uploader, a.meta["album"], a.meta["track"], b.meta["track"], a.cover_url),
                         ("Pitbull, Sensato", "Global Warming", "01", "02", "https://img/al"))
        r = spotify.analyze("https://open.spotify.com/playlist/xyz", Settings())
        self.assertEqual(len(r.entries), 100)
        self.assertIn("100", r.note)
        e = r.entries[0]
        self.assertEqual(e.cover_url, "")
        spotify.enrich(e)                       # fills cover + year from the track page
        self.assertEqual((e.cover_url, e.meta["year"]), ("https://img/big", "1987"))

    def test_score(self):
        s = lambda t, ch, d: spotify.score(t, ch, d, "Never Gonna Give You Up", "Rick Astley", 213)
        good = s("Rick Astley - Never Gonna Give You Up (Official Video)", "Rick Astley", 214)
        live = s("Rick Astley - Never Gonna Give You Up (Live)", "Rick Astley", 216)
        self.assertGreater(good, live)
        self.assertIsNone(s("Never Gonna Give You Up 1 hour loop", "x", 3600))


class History(unittest.TestCase):
    def test_archive(self):
        p = Path(tempfile.mkdtemp()) / "h.jsonl"
        a = Archive(p)
        a.add("youtube:abc", "audio", "Song", "C:/x.mp3")
        self.assertTrue(a.has("youtube:abc", "audio"))
        self.assertFalse(a.has("youtube:abc", "video"))
        b = Archive(p)                          # survives a restart
        self.assertEqual(b.get("youtube:abc")["path"], "C:/x.mp3")
        self.assertEqual(len(b), 1)
        b.clear()
        self.assertEqual(len(Archive(p)), 0)


class Installers(unittest.TestCase):
    def test_assets(self):
        self.assertEqual(deps.ytdlp_asset("Darwin", True), "yt-dlp_macos")
        self.assertEqual(deps.ytdlp_asset("Linux", True), "yt-dlp_linux_aarch64")
        self.assertEqual(deps.ytdlp_asset("Linux", False), "yt-dlp_linux")
        self.assertEqual(len(deps.ffmpeg_urls("Darwin", True)), 2)
        self.assertIn("arm64", deps.ffmpeg_urls("Darwin", True)[0])
        self.assertTrue(deps.ffmpeg_urls("Linux", False)[0].endswith("linux64-gpl.tar.xz"))

    def test_extract_tar_and_zip(self):
        d = Path(tempfile.mkdtemp())
        tx = d / "a.tar.xz"
        with tarfile.open(tx, "w:xz") as t:
            for n in ("ffmpeg-x/bin/ffmpeg", "ffmpeg-x/bin/ffprobe", "ffmpeg-x/doc/readme"):
                info = tarfile.TarInfo(n); info.size = 3
                t.addfile(info, io.BytesIO(b"bin"))
        out = d / "out"; out.mkdir()
        deps._extract(tx, out, {"ffmpeg", "ffprobe"})
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["ffmpeg", "ffprobe"])
        z = d / "b.zip.part"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("ffprobe", b"x")
        deps._extract(z, out, {"ffprobe"})


FAKE = r'''import sys, json, subprocess
a = sys.argv
if "-J" in a:
    q = a[-1]
    if "--flat-playlist" in a:          # searches
        if "music.youtube.com" in q:
            print(json.dumps({"entries": [{"id": "COVERCOVER1", "title": "Never Gonna Give You Up"}]}))
        else:
            print(json.dumps({"entries": [
                {"id": "LOOPLOOPLO1", "title": "Never Gonna Give You Up 10 hours", "duration": 36000, "channel": "x"},
                {"id": "dQw4w9WgXcQ", "title": "Rick Astley - Never Gonna Give You Up (Official Video)", "duration": 214, "channel": "Rick Astley"}]}))
    else:                               # fetch_info
        vid = q.split("v=")[1]
        if vid == "COVERCOVER1":        # wrong duration -> must be rejected
            print(json.dumps({"id": vid, "title": "Never Gonna Give You Up (Cover)", "channel": "Some Band", "duration": 180}))
        else:
            print(json.dumps({"id": vid, "title": "Rick Astley - Never Gonna Give You Up (Official Video)",
                              "channel": "Rick Astley", "duration": 214, "upload_date": "20091025", "extractor_key": "Youtube"}))
    sys.exit(0)
out = a[a.index("-o") + 1].replace("%(id)s", a[-1].split("v=")[1]).replace("%(ext)s", "m4a")
print("[download] Destination: " + out)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=1", "-c:a", "aac", out], check=True)
dst = out.rsplit(".", 1)[0] + ".mp3"
print("[ExtractAudio] Destination: " + dst)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out, dst], check=True)
'''


class SpotifyPipeline(unittest.TestCase):
    def test_download(self):
        from mutagen.id3 import ID3
        d = Path(tempfile.mkdtemp()); fake = d / "yt-dlp.py"; fake.write_text(FAKE)
        ff = Path(shutil.which("ffmpeg")); tools = Tools(fake, ff, ff)
        orig_get, orig_cover = spotify._get, thumbnails.fetch_cover
        spotify._get = lambda url, *a, **k: embed_html(TRACK)
        from PIL import Image
        b = io.BytesIO(); Image.new("RGB", (64, 64), "green").save(b, "JPEG")
        covers = []
        thumbnails.fetch_cover = lambda vid, url="", youtube=True: covers.append((vid, url, youtube)) or b.getvalue()
        try:
            r = spotify.analyze("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT", Settings())
            spec = JobSpec(r.entries[0], "audio", "mp3", "320", "{artist} - {title}", str(d / "out"))
            states = []
            path = Pipeline(spec, Settings(genre_online=False), tools, on_state=states.append).run()
        finally:
            spotify._get, thumbnails.fetch_cover = orig_get, orig_cover
        self.assertEqual(path.name, "Rick Astley - Never Gonna Give You Up.mp3")
        self.assertEqual(states[0], JobState.SEARCHING)
        self.assertEqual(covers, [("", "https://img/big", False)])   # Spotify cover, not the YouTube thumbnail
        t = ID3(path)
        self.assertEqual((str(t["TIT2"]), str(t["TPE1"]), str(t["TDRC"])),
                         ("Never Gonna Give You Up", "Rick Astley", "1987"))

    def test_video_only_youtube(self):
        from app.errors import AppError
        from app.models import Entry
        spec = JobSpec(Entry("1", "https://soundcloud.com/a/b", "t", source="soundcloud"), "video", "mp4", "best", "{title}", tempfile.mkdtemp())
        with self.assertRaises(AppError):
            Pipeline(spec, Settings(), Tools()).run()

    def test_overrides(self):
        m = tagger.apply_overrides(tagger.TrackMeta(title="t", artist="a", album="t"), {"album": "Real", "track": "03", "year": ""})
        self.assertEqual((m.album, m.track, m.album_artist), ("Real", "03", "a"))


if __name__ == "__main__":
    unittest.main()
