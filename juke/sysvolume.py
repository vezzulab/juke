"""The computer's own volume, followed in both directions.

The volume keys of a keyboard, the panel's volume applet and the mixer all change the volume of the sound card (the
default output), not of Juke. So that Juke's slider moves together with them, and moves them in turn, the slider
shows that volume: ``pactl subscribe`` (PulseAudio and PipeWire's Pulse layer) tells us the moment it changes, so
nothing is polled and an idle Juke wakes up for nothing.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

SINK = "@DEFAULT_SINK@"
_PERCENT = re.compile(r"(\d+)%")


def _pactl(*args: str, timeout: float = 1.5) -> str | None:
    try:
        return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=timeout, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None


class SystemVolume(QObject):
    changed = Signal(int, bool)          # volume 0..100, muted: the computer's volume moved (or we moved it)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.available = shutil.which("pactl") is not None and _pactl("get-sink-mute", SINK) is not None
        self._watcher: QProcess | None = None
        self._wanted = False
        self._last: tuple[int, bool] | None = None
        self._pending: int | None = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(70)           # a held volume key is a burst of events: read once at the end of it
        self._debounce.timeout.connect(self.refresh)
        self._send = QTimer(self)
        self._send.setSingleShot(True)
        self._send.setInterval(35)               # dragging the slider: one command per 35 ms, not one per pixel
        self._send.timeout.connect(self._flush)

    # -- reading ---------------------------------------------------------------------------------
    @staticmethod
    def read() -> tuple[int, bool] | None:
        volume, muted = _pactl("get-sink-volume", SINK), _pactl("get-sink-mute", SINK)
        match = _PERCENT.search(volume or "")
        if match is None:
            return None
        return min(100, int(match.group(1))), "yes" in (muted or "").lower()

    def refresh(self) -> None:
        state = self.read()
        if state is not None and state != self._last:
            self._last = state
            self.changed.emit(*state)

    # -- writing ---------------------------------------------------------------------------------
    def set_volume(self, volume: int) -> None:
        self._pending = max(0, min(100, int(volume)))
        self._send.start()

    def _flush(self) -> None:
        if self._pending is None:
            return
        volume, self._pending = self._pending, None
        self._last = (volume, self._last[1] if self._last else False)    # our own change is not news
        QProcess.startDetached("pactl", ["set-sink-volume", SINK, f"{volume}%"])

    def set_muted(self, muted: bool) -> None:
        self._last = (self._last[0] if self._last else 0, bool(muted))
        QProcess.startDetached("pactl", ["set-sink-mute", SINK, "1" if muted else "0"])

    # -- watching ---------------------------------------------------------------------------------
    def start(self) -> None:
        self._wanted = True
        if not self.available or (self._watcher is not None and self._watcher.state() != QProcess.NotRunning):
            return
        watcher = QProcess(self)
        watcher.setProgram("pactl")
        watcher.setArguments(["subscribe"])
        watcher.readyReadStandardOutput.connect(self._lines)
        watcher.finished.connect(self._ended)
        self._watcher = watcher
        watcher.start()

    def stop(self) -> None:
        self._wanted = False
        self._debounce.stop()
        watcher, self._watcher = self._watcher, None
        if watcher is not None:
            watcher.finished.disconnect(self._ended)
            watcher.kill()
            watcher.deleteLater()

    def _lines(self) -> None:
        if self._watcher is None:
            return
        text = bytes(self._watcher.readAllStandardOutput()).decode("utf-8", "replace")
        if any(" on sink #" in line or " on server" in line for line in text.splitlines()):
            self._debounce.start()

    def _ended(self, *_args) -> None:
        """The sound server restarted (or pactl died): look again in a moment, once, if we still want to follow."""
        self._watcher = None
        if self._wanted:
            QTimer.singleShot(3000, lambda: self.start() if self._wanted else None)
