from __future__ import annotations
import json
import logging
from dataclasses import dataclass, asdict, fields

from . import paths


@dataclass
class Settings:
    # Downloads
    download_dir: str = ""
    audio_format: str = "mp3"          # mp3 | m4a | flac
    audio_quality: str = "320"         # mp3 bitrate: 320 | 256 | 192
    video_quality: str = "best"        # best | 1080 | 720 | 480 | 360
    naming_template: str = "{artist} - {title}"
    ask_naming: bool = True
    skip_downloaded: bool = True       # history: leave already downloaded items unchecked
    # Metadata
    embed_thumbnail: bool = True
    write_id3: bool = True
    save_thumbnail_separately: bool = False
    auto_detect_artist: bool = True
    crop_cover_square: bool = True
    cap_bitrate_to_source: bool = False
    write_comment: bool = True
    tag_comment: str = "www DaveeB YT Downloader"
    write_genre_tag: bool = False      # genre is used for sorting; writing it to the tag is optional
    # Organization
    sort_template: str = "{genre}"     # sub-folders inside the output folder; "" = none
    genre_online: bool = True          # MusicBrainz lookup when YouTube gives no genre
    unknown_genre: str = "Unsorted"
    # Spotify (optional own API keys -> whole playlists, album names, track numbers)
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    # Phone / web access (server inside the app, same Wi-Fi only)
    web_enabled: bool = False
    web_port: int = 8765
    web_token: str = ""
    # Appearance
    theme: str = "dark"                # dark | light | system
    clipboard_watch: bool = True
    # Advanced
    ytdlp_path: str = ""
    ffmpeg_path: str = ""
    max_parallel: int = 2
    custom_args: str = ""

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        try:
            data = json.loads(paths.settings_file().read_text(encoding="utf-8"))
            names = {f.name for f in fields(cls)}
            for k, v in data.items():
                if k in names and isinstance(v, type(getattr(s, k))):
                    setattr(s, k, v)
        except FileNotFoundError:
            pass
        except Exception:
            logging.exception("Could not load settings, using defaults")
        if not s.download_dir:
            s.download_dir = str(paths.default_music_dir())
        s.max_parallel = min(8, max(1, s.max_parallel))
        return s

    def save(self) -> None:
        paths.settings_file().write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
