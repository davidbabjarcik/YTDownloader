"""One download job: fetch -> convert -> tag -> embed cover -> rename. No Qt here."""
from __future__ import annotations
import dataclasses
import logging
import shutil
import uuid
from pathlib import Path

from . import genre, naming, tagger, thumbnails, ytdlp
from .errors import AppError, Cancelled, classify
from .models import JobState, fmt_eta, fmt_size, fmt_speed


class Pipeline:
    def __init__(self, spec, settings, tools, on_state=None, on_progress=None):
        self.spec, self.settings, self.tools = spec, settings, tools
        self.on_state = on_state or (lambda s: None)
        self.on_progress = on_progress or (lambda *a: None)
        self.runner = ytdlp.ProcessRunner()
        self.warnings: list[str] = []
        self._stream = 0
        self._streams = 2 if spec.kind == "video" else 1

    def cancel(self) -> None:
        self.runner.cancel()

    def _check(self) -> None:
        if self.runner.cancelled:
            raise Cancelled()

    def _on_line(self, line: str) -> None:
        if line.startswith("[download] Destination:"):
            self._stream += 1
        p = ytdlp.parse_progress(line)
        if p:
            frac = (p.downloaded / p.total) if (p.downloaded and p.total) else 0.0
            idx = max(self._stream - 1, 0)
            pct = min(99.0, (idx + min(frac, 1.0)) / self._streams * 100)
            self.on_progress(pct, fmt_speed(p.speed), fmt_eta(p.eta), fmt_size(p.total))
        elif line.startswith(ytdlp.STAGE_PREFIXES):
            self.on_state(JobState.CONVERTING)
            self.on_progress(99.0, "", "", "")

    def run(self) -> Path:
        s, spec = self.settings, self.spec
        self.on_state(JobState.DOWNLOADING)
        info = spec.entry.info
        if info is None:
            info = ytdlp.fetch_info(spec.entry.url, self.tools, s)
        self._check()
        meta = tagger.detect_meta(info, s.auto_detect_artist)
        if s.write_genre_tag or "{genre}" in (spec.sort_template + spec.template):
            try:
                meta.genre = genre.detect_genre(info, meta, s.genre_online, s.unknown_genre)
            except Exception:  # noqa: BLE001
                logging.exception("genre detection failed")
                meta.genre = s.unknown_genre
        src_abr, _ = ytdlp.audio_summary(info)
        out_dir = Path(spec.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp = out_dir / f".ytdl_{uuid.uuid4().hex[:8]}"
        tmp.mkdir()
        try:
            cmd = ytdlp.build_download_cmd(self.tools, s, spec, tmp, src_abr)
            rc, lines = self.runner.run(cmd, self._on_line)
            self._check()
            if rc != 0:
                raise classify("\n".join(lines[-60:]))
            ext = spec.fmt if spec.kind == "audio" else "mp4"
            produced = self._find_output(tmp, meta.id or spec.entry.id, ext)
            ext = produced.suffix.lstrip(".").lower()

            self.on_state(JobState.EMBEDDING)
            cover = None
            want_embed = s.embed_thumbnail and spec.kind == "audio"
            if want_embed or s.save_thumbnail_separately:
                raw = thumbnails.fetch_cover(meta.id or spec.entry.id, info.get("thumbnail") or "")
                if raw:
                    try:
                        cover = thumbnails.prepare_cover(raw, s.crop_cover_square)
                    except Exception as e:  # noqa: BLE001
                        logging.exception("cover processing failed")
                        self.warnings.append(f"Cover art failed: {e}")
                else:
                    self.warnings.append("Thumbnail could not be downloaded")
            if s.write_id3 or (cover and want_embed):
                try:
                    tag_meta = dataclasses.replace(
                        meta, genre=meta.genre if (s.write_genre_tag and meta.genre != s.unknown_genre) else "")
                    comment = s.tag_comment if (s.write_id3 and s.write_comment) else ""
                    tagger.write_tags(produced, tag_meta, cover if want_embed else None,
                                      s.write_id3, comment)
                except Exception as e:  # noqa: BLE001
                    logging.exception("tagging failed")
                    self.warnings.append(f"Tagging failed: {e}")
            self._check()

            stem = naming.render(spec.template, meta.as_dict())
            dest_dir = out_dir.joinpath(*naming.render_folders(spec.sort_template, meta.as_dict()))
            dest_dir.mkdir(parents=True, exist_ok=True)
            final = naming.unique_path(dest_dir, stem, ext)
            shutil.move(str(produced), str(final))
            if cover and s.save_thumbnail_separately:
                final.with_suffix(".jpg").write_bytes(cover)
            self.on_progress(100.0, "", "", fmt_size(final.stat().st_size))
            return final
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _find_output(tmp: Path, vid: str, ext: str) -> Path:
        cand = tmp / f"{vid}.{ext}"
        if cand.exists():
            return cand
        files = [p for p in tmp.iterdir()
                 if p.is_file() and p.suffix.lower() not in (".part", ".ytdl", ".json", ".temp")]
        same = [p for p in files if p.suffix.lower() == f".{ext}"]
        pool = same or files
        if pool:
            return max(pool, key=lambda p: p.stat().st_size)
        raise AppError("DOWNLOAD_FAILED", "Download failed", "No output file was produced.")
