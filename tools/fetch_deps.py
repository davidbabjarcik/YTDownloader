"""Download yt-dlp.exe + ffmpeg.exe + ffprobe.exe into a folder (used by build.bat).
Usage: python tools/fetch_deps.py bin"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import deps  # noqa: E402


def progress(label, done, total):
    if total:
        print(f"\r{label}: {done / total * 100:5.1f}%", end="", flush=True)


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "bin").resolve()
    target.mkdir(parents=True, exist_ok=True)
    if not (target / "yt-dlp.exe").exists():
        deps.install_ytdlp(target, progress); print()
    if not ((target / "ffmpeg.exe").exists() and (target / "ffprobe.exe").exists()):
        deps.install_ffmpeg(target, progress); print()
    print("Components in", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
