"""What is already on a phone or tablet, read the way the phone lays it out: Music/<Artist>/<Album>/<song>.

Nothing is downloaded: names and folders say enough (a device is not asked for the tags of thousands of files), and
that is exactly how Juke itself files what it sends."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable

from . import mtp

# the folders a phone keeps songs in, and how deep to look in each (Music is a library; the others are just a place)
ROOTS = {"Music": 6, "Podcasts": 4, "Audiobooks": 4, "Download": 3, "Recordings": 3}
NUMBER = re.compile(r"^\d{1,3}\s*[-._)]*\s+")


@dataclass(slots=True)
class Song:
    artist: str
    album: str
    title: str
    filename: str
    size: int
    storage: int              # id of the storage it is on
    storage_name: str
    ref: object               # how the backend reaches the file (to delete it)


def describe(root: str, parts: list[str]) -> tuple[str, str, str]:
    """(artist, album, title) from the path of a song below ``root``: parts = ["Artist", "Album", "01 Song.mp3"]."""
    title = NUMBER.sub("", os.path.splitext(parts[-1])[0]).strip() or os.path.splitext(parts[-1])[0]
    folders = parts[:-1]
    if root != "Music":                       # Downloads, podcasts...: no artist, the folders are the "album"
        return root, "/".join(folders), title
    if not folders:
        return "", "", title
    return folders[0], "/".join(folders[1:]), title


def scan(device: mtp.Device, extensions: set[str] | frozenset[str], progress: Callable[[int], None] = lambda n: None,
         cancelled: Callable[[], bool] = lambda: False) -> list[Song]:
    """Every song in the usual folders of every storage of the device."""
    songs: list[Song] = []
    with mtp.open_session(device) as session:
        for storage in session.storages():
            top = session.children(storage.id, session.root(storage.id))
            for name, depth in ROOTS.items():
                entry = top.get(name)
                if entry is None or not entry.is_folder:
                    continue
                stack = [(entry.ref, [], 1)]
                while stack:
                    if cancelled():
                        return songs
                    ref, parts, level = stack.pop()
                    for child in sorted(session.children(storage.id, ref).values(), key=lambda e: e.name.casefold(), reverse=True):
                        if child.is_folder:
                            if level < depth:
                                stack.append((child.ref, parts + [child.name], level + 1))
                        elif os.path.splitext(child.name)[1].lower() in extensions:
                            artist, album, title = describe(name, parts + [child.name])
                            songs.append(Song(artist, album, title, child.name, child.size, storage.id, storage.name, child.ref))
                    progress(len(songs))
    return songs


def remove(device: mtp.Device, songs: list[Song], cancelled: Callable[[], bool] = lambda: False) -> tuple[int, int]:
    """Delete these songs from the device. Returns (removed, failed)."""
    removed = failed = 0
    with mtp.open_session(device) as session:
        for song in songs:
            if cancelled():
                break
            try:
                session.delete(song.storage, song.ref)
                removed += 1
            except mtp.MtpError:
                failed += 1
    return removed, failed
