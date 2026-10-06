"""Which songs can be played right now.

A song from Airsonic needs the server (and the internet or the network that leads to it); a local song needs its file,
which may live on a NAS or a drive that is not plugged in. The list shows the ones that cannot be played in grey, with
a note, instead of letting the person find out by pressing play.

Nothing here polls. Files are looked at only for the rows that are on screen, in a background thread (a network
folder that does not answer can take a long time, and the window must not wait for it), and the answer is kept for a
little while. The server is asked when the network changes, when the window comes back to the front, or when a song of
it fails; ``set_server`` is how the window reports what it found.
"""

from __future__ import annotations

import os
import threading
import time

from PySide6.QtCore import QObject, Signal

from .db.database import SOURCE_AIRSONIC, Track

FILE_TTL_S = 30.0          # how long "this file is there / is not there" is trusted before looking again


def _check(paths: list[str]) -> dict[str, bool]:
    """Does each file exist? Folders are asked first, so a drive that is not connected costs one question, not one per song."""
    folders: dict[str, bool] = {}
    result: dict[str, bool] = {}
    for path in paths:
        folder = os.path.dirname(path)
        if folder not in folders:
            try:
                folders[folder] = os.path.isdir(folder)
            except OSError:
                folders[folder] = False
        if not folders[folder]:
            result[path] = False
            continue
        try:
            result[path] = os.path.isfile(path)
        except OSError:
            result[path] = False
    return result


class Availability(QObject):
    changed = Signal()                  # something became playable or not: repaint the lists
    _done = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.server_online: bool | None = None          # None: not known yet, treated as reachable
        self._files: dict[str, tuple[bool, float]] = {}
        self._wanted: set[str] = set()
        self._busy = False
        self._lock = threading.Lock()
        self._done.connect(self._finished)

    # -- what the list asks ---------------------------------------------------------------------------
    def reason(self, track: Track) -> str | None:
        """``"server"`` (an Airsonic song while the server cannot be reached), ``"file"`` (a local file that is not
        there) or None when it can be played."""
        if track.source_type == SOURCE_AIRSONIC:
            return "server" if self.server_online is False else None
        hit = self._files.get(track.location)
        return "file" if hit is not None and not hit[0] else None

    def want(self, tracks: list[Track | None]) -> None:
        """Look (in the background) at the local files of these rows, unless they were looked at a moment ago."""
        now = time.monotonic()
        fresh = [t.location for t in tracks if t is not None and t.source_type != SOURCE_AIRSONIC
                 and (t.location not in self._files or now - self._files[t.location][1] > FILE_TTL_S)]
        if not fresh:
            return
        with self._lock:
            self._wanted.update(fresh)
            if self._busy:
                return
            self._busy = True
        threading.Thread(target=self._work, name="juke-availability", daemon=True).start()

    def _work(self) -> None:
        while True:
            with self._lock:
                batch = sorted(self._wanted)
                self._wanted.clear()
                if not batch:
                    self._busy = False
                    return
            self._done.emit(_check(batch))

    def _finished(self, results: dict) -> None:
        now = time.monotonic()
        flipped = False
        for path, ok in results.items():
            before = self._files.get(path)
            self._files[path] = (ok, now)
            flipped = flipped or (before is not None and before[0] != ok) or (before is None and not ok)
        if flipped:
            self.changed.emit()

    # -- what the window reports ------------------------------------------------------------------------
    def set_server(self, online: bool | None) -> bool:
        """The server answered (True) or did not (False). Returns whether that is news."""
        if online == self.server_online:
            return False
        self.server_online = online
        self.changed.emit()
        return True

    def expire(self) -> None:
        """A drive may have been plugged in or out: what is known stays on screen, but is looked at again."""
        self._files = {path: (ok, 0.0) for path, (ok, _t) in self._files.items()}
