"""Local library indexer: tag reading, cover extraction and the background scanner.

The scan runs entirely inside a QThread; it only talks to the GUI through
signals, so the interface never blocks however large the collection is.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QThread, Qt, Signal
from PySide6.QtGui import QImage

from ..config import AUDIO_EXTENSIONS, COVERS_DIR
from .database import SOURCE_LOCAL, Database

COVER_SIZE = 320
_FOLDER_ART = ("cover", "folder", "front", "album", "albumart")
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")

_ID3_FRAMES = {
    "title": "TIT2", "artist": "TPE1", "album": "TALB",
    "genre": "TCON", "date": "TDRC", "tracknumber": "TRCK",
}


def _first(tags, key: str) -> str:
    """First value of ``key`` for EasyID3/Vorbis/EasyMP4 tags or raw ID3 frames."""
    if tags is None:
        return ""
    from mutagen.id3 import ID3   # mutagen is only imported once a file is actually read
    try:
        value = tags.get(key)
        if value is None and isinstance(tags, ID3):
            value = tags.get(_ID3_FRAMES[key])
    except (KeyError, ValueError):
        return ""
    if value is None:
        return ""
    if hasattr(value, "text"):
        value = value.text
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value).strip()


def _leading_int(text: str) -> int:
    match = re.match(r"\s*(\d+)", text)
    return int(match.group(1)) if match else 0


def read_tags(path: str | os.PathLike) -> dict | None:
    """Unified metadata for one audio file, or None if mutagen cannot parse it."""
    import mutagen

    try:
        audio = mutagen.File(path, easy=True)
    except Exception:  # corrupt files raise assorted mutagen/OS errors
        return None
    if audio is None:
        return None
    tags = audio.tags
    info = audio.info
    title = _first(tags, "title") or Path(path).stem
    date = _first(tags, "date")
    bitrate = int(getattr(info, "bitrate", 0) or 0)
    return {
        "title": title,
        "artist": _first(tags, "artist") or _first(tags, "albumartist"),
        "album": _first(tags, "album"),
        "genre": _first(tags, "genre"),
        "year": _leading_int(date),
        "track_no": _leading_int(_first(tags, "tracknumber")),
        "duration": float(getattr(info, "length", 0.0) or 0.0),
        "bitrate": bitrate // 1000 if bitrate > 1000 else bitrate,
    }


def write_tags(path: str | os.PathLike, fields: dict) -> None:
    """Write title/artist/album/genre/year/track_no back into the file."""
    import mutagen
    from mutagen.id3 import ID3

    audio = mutagen.File(path, easy=True)
    if audio is None:
        raise ValueError("unsupported file")
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    easy_keys = {"title": "title", "artist": "artist", "album": "album", "genre": "genre",
                 "year": "date", "track_no": "tracknumber"}
    for field, easy_key in easy_keys.items():
        if field not in fields:
            continue
        value = fields[field]
        text = "" if value in (0, None) else str(value)
        if isinstance(tags, ID3):
            from mutagen import id3
            frame_cls = getattr(id3, _ID3_FRAMES[easy_key])
            tags.delall(_ID3_FRAMES[easy_key])
            if text:
                tags.add(frame_cls(encoding=3, text=[text]))
        elif text:
            tags[easy_key] = [text]
        elif easy_key in tags:
            del tags[easy_key]
    audio.save()


def prepare_cover(data: bytes, limit: int = 1200) -> bytes | None:
    """A picked image as a JPEG of at most ``limit`` pixels: what goes into the files and the cover cache."""
    image = QImage.fromData(data)
    if image.isNull():
        return None
    if max(image.width(), image.height()) > limit:
        image = image.scaled(limit, limit, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    return bytes(buffer.data()) if image.convertToFormat(QImage.Format_RGB32).save(buffer, "JPEG", 90) else None


def write_cover(path: str | os.PathLike, data: bytes | None) -> None:
    """Put ``data`` (a JPEG) in the file as its front cover; ``None`` takes the artwork out."""
    import mutagen
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import APIC, ID3
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.ogg import OggFileType

    audio = mutagen.File(path)
    if audio is None:
        raise ValueError("unsupported file")
    if isinstance(audio, FLAC):
        audio.clear_pictures()
        if data:
            audio.add_picture(_picture(Picture, data))
    elif isinstance(audio, MP4):
        if data:
            audio["covr"] = [MP4Cover(data, imageformat=MP4Cover.FORMAT_JPEG)]
        elif "covr" in audio:
            del audio["covr"]
    elif isinstance(audio, OggFileType):
        if "metadata_block_picture" in (audio.tags or {}):
            del audio["metadata_block_picture"]
        if data:
            audio["metadata_block_picture"] = [base64.b64encode(_picture(Picture, data).write()).decode("ascii")]
    else:
        if audio.tags is None:
            audio.add_tags()
        if not isinstance(audio.tags, ID3):
            raise ValueError("unsupported file")
        audio.tags.delall("APIC")
        if data:
            audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=data))
    audio.save()


def _picture(cls, data: bytes):
    picture = cls()
    picture.type, picture.mime, picture.desc, picture.data = 3, "image/jpeg", "", data
    return picture


def cover_key_for(artist: str, album: str, path: str) -> str:
    """Album covers are shared between the tracks of an album."""
    base = f"{artist}|{album}" if album else path
    return hashlib.sha1(base.casefold().encode("utf-8")).hexdigest()[:20]


def cover_path(key: str) -> Path:
    return COVERS_DIR / f"{key}.jpg"


def extract_cover(path: str) -> bytes | None:
    """Embedded artwork bytes (ID3, FLAC, MP4, Vorbis) or a cover image next to the file."""
    import mutagen
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import ID3

    try:
        audio = mutagen.File(path)
    except Exception:
        audio = None
    data = None
    if audio is not None:
        tags = audio.tags
        try:
            if isinstance(audio, FLAC) and audio.pictures:
                data = audio.pictures[0].data
            elif isinstance(tags, ID3):
                frames = tags.getall("APIC")
                data = frames[0].data if frames else None
            elif tags is not None and "covr" in tags:
                data = bytes(tags["covr"][0])
            elif tags is not None and "metadata_block_picture" in tags:
                data = Picture(base64.b64decode(tags["metadata_block_picture"][0])).data
        except Exception:
            data = None
    if data:
        return data
    folder = Path(path).parent
    try:
        for entry in sorted(folder.iterdir()):
            if entry.suffix.lower() in _IMAGE_EXT and entry.stem.lower() in _FOLDER_ART:
                return entry.read_bytes()
    except OSError:
        pass
    return None


def save_cover(key: str, data: bytes) -> bool:
    """Scale ``data`` to a JPEG thumbnail in the cover cache."""
    image = QImage.fromData(data)
    if image.isNull():
        return False
    image = image.scaled(COVER_SIZE, COVER_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    return image.save(str(cover_path(key)), "JPEG", 88)


def iter_audio_files(roots: list[str], should_stop=lambda: False):
    """Yield (path, mtime, size) for audio files below ``roots`` (symlink loops safe)."""
    seen: set[tuple[int, int]] = set()
    for root in roots:
        stack = [root]
        while stack and not should_stop():
            current = stack.pop()
            try:
                stat = os.stat(current)
                ident = (stat.st_dev, stat.st_ino)
                if ident in seen:
                    continue
                seen.add(ident)
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            if entry.is_dir(follow_symlinks=True):
                                if not entry.name.startswith(".") and not entry.name.endswith(".juke"):
                                    stack.append(entry.path)
                            elif os.path.splitext(entry.name)[1].lower() in AUDIO_EXTENSIONS:
                                st = entry.stat()
                                yield entry.path, st.st_mtime, st.st_size
                        except OSError:
                            continue
            except OSError:
                continue


class LibraryScanner(QThread):
    """Incremental scan: new/changed files are read, vanished files are removed."""

    progress = Signal(int, int)          # processed, total
    scan_finished = Signal(int, int, int)  # added/updated, removed, total files seen
    failed = Signal(str)

    BATCH = 200
    folders_synced = Signal()            # the mirrored folders (Music.juke) changed

    def __init__(self, db: Database, roots: list[str], parent=None, *, folders=None,
                 extra_files: list[str] | None = None, prune: bool = True) -> None:
        """``roots`` are walked; ``extra_files`` (songs dropped in from elsewhere) are indexed as well.

        With ``prune`` False songs that are not under ``roots`` are left alone: that is how a few
        dropped files are added without the scan treating the rest of the library as gone.
        """
        super().__init__(parent)
        self._db = db
        self._roots = [r for r in roots if r]
        self._folders = folders
        self._extra = list(extra_files or [])
        self._prune = prune
        self._stop = False

    def cancel(self) -> None:
        self._stop = True

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            self._scan()
        except Exception as exc:  # surfaced to the UI rather than dying silently
            self.failed.emit(str(exc))
        finally:
            self._db.close_thread_connection()
            if self._folders is not None:
                self._folders.close_thread_connection()

    def _scan(self) -> None:
        known = self._db.local_index()
        files = list(iter_audio_files(self._roots, lambda: self._stop))
        if self._folders is not None:                       # what the user removed from Juke stays out of it
            skip = tuple(d.rstrip(os.sep) + os.sep for d in self._folders.hidden_dirs())
            if skip:
                files = [f for f in files if not f[0].startswith(skip)]
        present = {path for path, _, _ in files}
        if self._folders is not None and self._prune and not self._stop:
            # the folders that mirror the music directories follow the disk, before any tag is read
            if self._folders.sync_roots(self._roots, present):
                self.folders_synced.emit()
        for extra in self._extra:
            try:
                st = os.stat(extra)
            except OSError:
                continue
            if extra not in present:
                files.append((extra, st.st_mtime, st.st_size))
        todo = [f for f in files if known.get(f[0]) != (f[1], f[2])]
        total = len(todo)
        batch: list[dict] = []
        done = 0
        covered: set[str] = set()
        for path, mtime, size in todo:
            if self._stop:
                break
            tags = read_tags(path)
            done += 1
            if tags is None:
                continue
            key = cover_key_for(tags["artist"], tags["album"], path)
            if key not in covered:
                covered.add(key)
                if not cover_path(key).exists():
                    data = extract_cover(path)
                    if not (data and save_cover(key, data)):
                        key = ""
            elif not cover_path(key).exists():
                key = ""
            batch.append({
                "source_type": SOURCE_LOCAL, "location": path, "cover_key": key,
                "mtime": mtime, "size": size, **tags,
            })
            if len(batch) >= self.BATCH:
                self._db.upsert_many(batch)
                batch.clear()
                self.progress.emit(done, total)
        if batch:
            self._db.upsert_many(batch)
        self.progress.emit(done, total)
        removed = 0
        if not self._stop and self._prune:
            stale = [loc for loc in known if loc not in present]
            removed = self._db.delete_locations(SOURCE_LOCAL, stale)
        self.scan_finished.emit(done, removed, len(files))
