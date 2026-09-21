"""Copy songs onto a phone or tablet: Music/<folder>/<song>, one folder deep and never a folder inside a folder, skipping
what is already there. <folder> is the Juke folder (or the folder on disk) the songs were sent from, or their artist."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import unquote

from . import mtp

TYPES = {"audio/mpeg": ".mp3", "audio/flac": ".flac", "audio/x-flac": ".flac", "audio/ogg": ".ogg", "audio/opus": ".opus",
         "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/aac": ".aac", "audio/wav": ".wav", "audio/x-wav": ".wav"}
BAD = re.compile(r'[\x00-\x1f\\/:*?"<>|]+')


@dataclass(slots=True)
class Item:
    """One song to send. It is a local ``path`` or a server ``url`` (downloaded first, then sent)."""

    name: str                 # file name on the device; for a url without its extension, which the server tells us
    artist: str = ""
    album: str = ""
    path: str = ""
    url: str = ""
    folder: str = ""          # the name of the one folder on the device they go into; the artist's name when empty
    cover_url: str = ""       # where the server keeps the cover, for a song that comes from it
    cover_key: str = ""       # the library's cached cover of the song, when the file itself has none


@dataclass(slots=True)
class Result:
    sent: int = 0
    skipped: int = 0          # already on the device
    failed: list[str] = field(default_factory=list)
    cancelled: bool = False
    storage: str = ""          # where it went: the name of the internal memory or the card
    storages: list = field(default_factory=list)


def clean(text: str, fallback: str) -> str:
    """A name a phone's file system accepts."""
    text = BAD.sub("_", text or "").strip().strip(".")[:120].strip()
    return text or fallback


def _cover(item: Item, source: str) -> bytes | None:
    """The cover of this song as a JPEG ready to go inside the file: the server's, the one next to the file, or the
    library's own copy. None when there is none."""
    from ..db import indexer

    data = None
    if item.cover_url:
        try:
            request = urllib.request.Request(item.cover_url, headers={"User-Agent": "Juke"})
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
        except (OSError, ValueError):
            data = None
    if not data:
        data = indexer.extract_cover(source)
    if not data and item.cover_key:
        cached = indexer.cover_path(item.cover_key)
        data = cached.read_bytes() if cached.is_file() else None
    return indexer.prepare_cover(data) if data else None


def _with_cover(item: Item, source: str, temporary: bool) -> str:
    """The file to send: ``source`` if it already carries its cover; otherwise a copy that does (an original of the
    person's is never touched). ``temporary`` says ``source`` is already a copy of ours, changed in place. Any trouble
    with the picture only means the song goes without it."""
    from ..db import indexer

    try:
        if indexer.embedded_cover(source):
            return source
        data = _cover(item, source)
        if not data:
            return source
        target = source
        if not temporary:
            handle, target = tempfile.mkstemp(prefix="juke-cover-", suffix=os.path.splitext(source)[1])
            os.close(handle)
            shutil.copyfile(source, target)
        try:
            indexer.write_cover(target, data)
        except Exception:
            if target != source:
                os.unlink(target)
            return source
        return target
    except Exception:
        return source


def _from_tags(item: Item) -> None:
    """A file picked from disk brings no artist with it: read it from the tags."""
    if item.artist:
        return
    from ..db.indexer import read_tags

    tags = read_tags(item.path) or {}
    item.artist = tags.get("artist", "")


def extension(disposition: str, ctype: str) -> str:
    """The extension of a downloaded song, from the server's own file name (plain, quoted, RFC 5987 or the encoded form
    ``=?UTF-8?Q?name.mp3?=`` that Airsonic sends), else from the kind of file it says it is, else ".mp3"."""
    from email.header import decode_header, make_header

    from ..config import AUDIO_EXTENSIONS

    name = ""
    star = re.search(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", disposition, re.I)
    plain = re.search(r'filename\s*=\s*(?:"([^"]*)"|([^;]+))', disposition, re.I)
    if star:
        name = unquote(star.group(1).strip().strip('"'))
    elif plain:
        name = (plain.group(1) if plain.group(1) is not None else plain.group(2)).strip()
    try:
        name = str(make_header(decode_header(name)))
    except Exception:
        pass
    found = os.path.splitext(name)[1].lower()
    return found if found in AUDIO_EXTENSIONS else TYPES.get(ctype, ".mp3")


def _download(item: Item, cancelled: Callable[[], bool], fraction: Callable[[float], None]) -> tuple[str, str]:
    """Fetch a server song into a temporary file. Returns (path, file name on the device)."""
    request = urllib.request.Request(item.url, headers={"User-Agent": "Juke"})
    handle, target = tempfile.mkstemp(prefix="juke-send-")
    try:
        with os.fdopen(handle, "wb") as out, urllib.request.urlopen(request, timeout=30) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                block = response.read(256 * 1024)
                if not block:
                    break
                if cancelled():
                    raise mtp.Cancelled(item.name)
                out.write(block)
                done += len(block)
                if total:
                    fraction(done / total * 0.5)          # the download is the first half of this song
            disposition = response.headers.get("Content-Disposition") or ""
            ctype = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        return target, item.name + extension(disposition, ctype)
    except BaseException:
        try:
            os.unlink(target)
        except OSError:
            pass
        raise


def send(device: mtp.Device, items: list[Item], progress: Callable[[int, int, str, float], None],
         cancelled: Callable[[], bool], storage_id: int | None = None, legacy: bool = True) -> Result:
    """Send ``items`` to the storage ``storage_id`` (the internal memory or a card; the first one that can be written to
    when none is given or it is gone). ``progress(done, total, name, fraction_of_this_song)`` is called as it goes.
    ``legacy=False`` sends even a song that an older layout (a folder inside the folder) already holds."""
    result = Result()
    total = len(items)
    in_a_row = 0
    with mtp.open_session(device) as session:
        writable = [s for s in session.storages() if s.writable]
        storage = next((s for s in writable if s.id == storage_id), writable[0] if writable else None)
        if storage is None:
            raise mtp.MtpError("the device has no storage to write to")
        result.storage = storage.name
        for index, item in enumerate(items):
            if cancelled():
                result.cancelled = True
                break
            progress(index, total, item.name, 0.0)
            temp = ""
            try:
                if item.path and not item.folder:
                    _from_tags(item)
                artist = clean(item.artist, "Unknown Artist")
                folder = session.folder(storage.id, ["Music", clean(item.folder, "") or artist])
                there = session.children(storage.id, folder)
                name = clean(item.name, "song")
                places = [there]
                for older in ({clean(item.artist, ""), clean(item.album, "")} - {""}) if legacy else ():   # what an earlier Juke made: a folder inside it
                    inside = there.get(older)
                    if inside is not None and inside.is_folder:
                        places.append(session.children(storage.id, inside.ref))
                if item.path and any(name in p and p[name].size >= os.path.getsize(item.path) for p in places):     # ≥: the cover added to it makes it a bit bigger
                    result.skipped += 1
                    continue
                if item.url:
                    if any(os.path.splitext(n)[0] == name for p in places for n in p):
                        result.skipped += 1
                        continue
                    source, name = _download(item, cancelled, lambda f: progress(index, total, item.name, f))
                    temp = source
                    name = clean(name, "song")
                    source = _with_cover(item, source, temporary=True)
                else:
                    source = _with_cover(item, item.path, temporary=False)
                    if source != item.path:
                        temp = source
                base = 0.5 if item.url else 0.0
                session.send(storage.id, folder, source, name,
                             lambda sent, size: not cancelled() and (progress(index, total, item.name, base + (sent / size if size else 1) * (1 - base)) or True))
                result.sent += 1
                in_a_row = 0
            except mtp.Cancelled:
                result.cancelled = True
                break
            except (mtp.MtpError, OSError):
                result.failed.append(item.name)
                in_a_row += 1
                if in_a_row >= 3:                      # the device is most likely gone: do not grind through the rest
                    result.failed.extend(i.name for i in items[index + 1:])
                    break
            finally:
                if temp:
                    try:
                        os.unlink(temp)
                    except OSError:
                        pass
        progress(total, total, "", 1.0)
        try:
            result.storages = session.storages()
        except Exception:
            pass
    return result
