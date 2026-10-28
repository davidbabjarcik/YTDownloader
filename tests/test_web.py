"""Web access server with a fake controller (no Qt, no network besides localhost)."""
import json, sys, tempfile, unittest, urllib.error, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import webserver
from app.models import AnalyzeResult, Entry, JobSpec, JobState


class FakeJob:
    def __init__(self, spec, path=None):
        self.id, self.spec, self.title = "job1", spec, spec.entry.title
        self.state = JobState.COMPLETED if path else JobState.DOWNLOADING
        self.percent, self.speed, self.eta, self.size = (100.0 if path else 40.0), "", "", ""
        self.message = self.detail = ""
        self.result = path


class FakeController(webserver.Controller):
    def __init__(self):
        self.queued, self.cancelled, self.job_list = [], [], []

    def analyze(self, urls):
        es = [Entry("a1", "https://soundcloud.com/x/a", "One", source="soundcloud"),
              Entry("b2", "https://soundcloud.com/x/b", "Two", source="soundcloud")]
        return [AnalyzeResult(urls[0], "Set", True, es)], []

    def is_downloaded(self, key, kind):
        return key == "soundcloud:a1" and kind == "audio"

    def enqueue(self, entries, kind, fmt, quality):
        self.queued.append(([e.id for e in entries], kind, fmt, quality))

    def jobs(self):
        return self.job_list

    def cancel(self, job_id):
        self.cancelled.append(job_id)


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = FakeController()
        cls.srv = webserver.WebServer(cls.c, "secret")
        cls.srv.start(0, "127.0.0.1")
        cls.base = f"http://127.0.0.1:{cls.srv.port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def req(self, path, body=None, token="secret"):
        r = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                   headers={"X-Token": token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def test_page_and_auth(self):
        code, body, h = self.req("/", token="")
        self.assertEqual(code, 200)
        self.assertIn(b"YT Downloader", body)
        self.assertEqual(self.req("/manifest.webmanifest")[0], 200)
        self.assertEqual(self.req("/api/state", token="wrong")[0], 401)
        self.assertEqual(self.req("/api/state", token="")[0], 401)
        self.assertEqual(self.req("/../app/settings.py")[0], 404)
        code, body, _ = self.req("/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["jobs"], [])

    def test_analyze_download_cancel(self):
        code, body, _ = self.req("/api/analyze", {"urls": "look https://soundcloud.com/x/sets/y"})
        a = json.loads(body)
        self.assertEqual(code, 200, a)
        self.assertEqual([i["title"] for i in a["items"]], ["One", "Two"])
        self.assertEqual(a["items"][0]["done"], {"audio": True, "video": False})
        self.assertFalse(a["has_youtube"])
        code, body, _ = self.req("/api/download", {"aid": a["aid"], "items": [1], "kind": "audio", "fmt": "mp3", "quality": "320"})
        self.assertEqual((code, json.loads(body)), (200, {"queued": 1}))
        self.assertEqual(self.c.queued[-1], (["b2"], "audio", "mp3", "320"))
        code, body, _ = self.req("/api/download", {"aid": a["aid"], "items": [0], "kind": "video", "fmt": "mp4"})
        self.assertEqual(code, 400)                     # video only for YouTube
        self.assertEqual(self.req("/api/download", {"aid": "nope", "items": [0]})[0], 400)
        self.assertEqual(self.req("/api/analyze", {"urls": "no link here"})[0], 400)
        self.req("/api/cancel", {"id": "job1"})
        self.assertEqual(self.c.cancelled, ["job1"])

    def test_file(self):
        f = Path(tempfile.mkdtemp()) / "Artist - Pieseň.mp3"
        f.write_bytes(b"ID3 data")
        spec = JobSpec(Entry("z", "u", "Pieseň"), "audio", "mp3", "320", "{title}", str(f.parent))
        self.c.job_list = [FakeJob(spec, f)]
        code, body, _ = self.req("/api/state")
        job = json.loads(body)["jobs"][0]
        self.assertTrue(job["ok"])
        self.assertEqual(job["file"], "Artist - Pieseň.mp3")
        code, body, h = self.req("/api/file/job1")
        self.assertEqual((code, body), (200, b"ID3 data"))
        self.assertIn("filename*=UTF-8''Artist%20-%20Piese%C5%88.mp3", h["Content-Disposition"])
        self.assertEqual(self.req("/api/file/other")[0], 404)
        self.c.job_list = []


if __name__ == "__main__":
    unittest.main()
