import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import naming
from app.errors import classify


class T(unittest.TestCase):
    def test_render(self):
        m = {"title": "Song: Live?", "artist": "A/B", "year": "2020", "id": "x"}
        self.assertEqual(naming.render("{artist} - {title}", m), "A-B - Song - Live")
        self.assertEqual(naming.render("{artist} - {title} ({year})", m), "A-B - Song - Live (2020)")

    def test_missing(self):
        m = {"title": "T", "artist": "", "year": "", "id": "x"}
        self.assertEqual(naming.render("{artist} - {title} ({year})", m), "T")
        self.assertEqual(naming.render("{artist}", {"id": "abc"}), "abc")

    def test_invalid_chars(self):
        out = naming.render("{title}", {"title": 'a\\b/c:d*e?f"g<h>i|j'})
        for ch in '\\/:*?"<>|':
            self.assertNotIn(ch, out)

    def test_folders(self):
        m = {"genre": "Hip-Hop", "artist": "A/B", "year": "", "album": "", "id": "x"}
        self.assertEqual(naming.render_folders("{genre}/{artist}", m), ["Hip-Hop", "A-B"])
        self.assertEqual(naming.render_folders("{genre}\\{year}\\{album}", m), ["Hip-Hop"])
        self.assertEqual(naming.render_folders("", m), [])
        self.assertEqual(naming.render_folders("../..", m), [])

    def test_errors(self):
        self.assertEqual(classify("ERROR: [youtube] x: Private video").code, "PRIVATE")
        self.assertEqual(classify("ERROR: Postprocessing: ffprobe and ffmpeg not found").code, "FFMPEG")
        self.assertEqual(classify("ERROR: getaddrinfo failed").code, "NETWORK")


if __name__ == "__main__":
    unittest.main()
