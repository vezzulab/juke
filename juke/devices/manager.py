"""Keeps the list of plugged-in phones and tablets up to date, and copies songs to them on background threads."""

from __future__ import annotations

import subprocess
import threading

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal

from ..config import AUDIO_EXTENSIONS
from . import library, mtp, transfer


class _Scan(QThread):
    found = Signal(object)

    def run(self) -> None:
        self.found.emit(mtp.scan())


class _Send(QThread):
    progress = Signal(int, int, str, float)
    finished_with = Signal(object)
    failed = Signal(str)

    def __init__(self, device: mtp.Device, items: list, storage_id: int | None, parent=None) -> None:
        super().__init__(parent)
        self.device, self.items, self.storage_id = device, items, storage_id
        self._stop = threading.Event()

    def cancel(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            self.finished_with.emit(transfer.send(self.device, self.items, self.progress.emit, self._stop.is_set, self.storage_id))
        except Exception as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)


class _Read(QThread):
    progress = Signal(int)
    found = Signal(object)
    failed = Signal(str)

    def __init__(self, device: mtp.Device, parent=None) -> None:
        super().__init__(parent)
        self.device = device
        self._stop = threading.Event()

    def cancel(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            self.found.emit(library.scan(self.device, AUDIO_EXTENSIONS, self.progress.emit, self._stop.is_set))
        except Exception as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)


class _Remove(QThread):
    finished_with = Signal(int, int)
    failed = Signal(str)

    def __init__(self, device: mtp.Device, songs: list, parent=None) -> None:
        super().__init__(parent)
        self.device, self.songs = device, songs

    def run(self) -> None:
        try:
            self.finished_with.emit(*library.remove(self.device, self.songs))
        except Exception as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)


class DeviceManager(QObject):
    """Polls the kernel's USB list (a few tiny reads, only while the window is in use) and asks libmtp about a device
    only when something was plugged in, unplugged or switched to another USB mode."""

    changed = Signal()
    progress = Signal(str, int, int, str, float)         # device key, songs done, songs in all, this one's name, its fraction
    sent = Signal(str, object)                           # device key, transfer.Result
    send_failed = Signal(str, str)                       # device key, why
    reading = Signal(str, int)                           # device key, songs found so far while reading what is on it
    songs = Signal(str, object)                          # device key, the songs on it (devices.library.Song)
    read_failed = Signal(str, str)                       # device key, why
    removed = Signal(str, int, int)                      # device key, songs removed, songs that could not be
    ejected = Signal(str, str)                           # device key, its name: it can be unplugged

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.devices: list[mtp.Device] = []
        self._signature: tuple | None = None
        self._scan: _Scan | None = None
        self._send: _Send | None = None
        self._read: _Read | None = None
        self._remove: _Remove | None = None
        self._ejected: set[str] = set()                   # put away by the person: hidden until it is unplugged and plugged in again
        self._eject_key = ""
        self._sending_key = ""
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.VeryCoarseTimer)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._tick)

    # -- the list
    def set_active(self, active: bool) -> None:
        """Only look while somebody is looking at the window (and right away when they come back to it)."""
        if not mtp.available():
            return
        if active:
            self._timer.start()
            self._tick()
        else:
            self._timer.stop()

    def _tick(self) -> None:
        signature = mtp.usb_signature()
        if signature != self._signature:
            self._signature = signature
            self.refresh()

    def refresh(self) -> None:
        """Ask again (the person may have closed the other program that held the device)."""
        if self._scan is not None or not mtp.available():
            return
        self._scan = _Scan(self)
        self._scan.found.connect(self._scanned)
        self._scan.finished.connect(self._scan_done)
        self._scan.start()

    def _scanned(self, found) -> None:
        if found is None:                                 # a transfer holds libmtp: what we knew still stands
            return
        self._ejected &= {d.key for d in found}           # one that was unplugged is forgotten: plugged in again it is new
        found = [d for d in found if d.key not in self._ejected]
        def summary(devices):                             # a card put in or taken out counts as a change too
            return [(d.key, d.state, d.label, tuple((s.id, s.name, s.writable) for s in d.storages)) for d in devices]

        old = summary(self.devices)
        self.devices = found
        if summary(found) != old:
            self.changed.emit()

    def _scan_done(self) -> None:
        if self._scan is not None:
            self._scan.deleteLater()
        self._scan = None

    def get(self, key: str) -> mtp.Device | None:
        return next((d for d in self.devices if d.key == key), None)

    def ready(self) -> list[mtp.Device]:
        return [d for d in self.devices if d.state == "ready"]

    # -- sending
    @property
    def sending(self) -> str:
        """The key of the device being written to, or ''."""
        return self._sending_key if self._send is not None else ""

    def send(self, key: str, items: list[transfer.Item], storage_id: int | None = None) -> bool:
        device = self.get(key)
        if device is None or device.state != "ready" or self._send is not None or not items:
            return False
        self._sending_key = key
        job = _Send(device, items, storage_id, self)
        job.progress.connect(lambda done, total, name, fraction: self.progress.emit(key, done, total, name, fraction))
        job.finished_with.connect(self._job_result)
        job.failed.connect(lambda why: self.send_failed.emit(key, why))
        job.finished.connect(self._job_done)
        self._send = job
        job.start()
        return True

    def cancel(self) -> None:
        if self._send is not None:
            self._send.cancel()

    # -- what is on the device
    @property
    def working(self) -> bool:
        return self._send is not None or self._remove is not None

    @property
    def reading_now(self) -> bool:
        return self._read is not None

    def read_songs(self, key: str) -> bool:
        """Read what the device already has (in the background). One read at a time; not while sending or removing."""
        device = self.get(key)
        if device is None or device.state != "ready" or self._read is not None or self.working:
            return False
        job = _Read(device, self)
        job.progress.connect(lambda n: self.reading.emit(key, n))
        job.found.connect(lambda found: self.songs.emit(key, found))
        job.failed.connect(lambda why: self.read_failed.emit(key, why))
        job.finished.connect(self._read_done)
        self._read = job
        job.start()
        return True

    def _read_done(self) -> None:
        job, self._read = self._read, None
        if job is not None:
            job.deleteLater()

    def remove(self, key: str, songs: list) -> bool:
        device = self.get(key)
        if device is None or device.state != "ready" or self.working or not songs:
            return False
        job = _Remove(device, songs, self)
        job.finished_with.connect(lambda done, failed: self.removed.emit(key, done, failed))
        job.failed.connect(lambda why: self.read_failed.emit(key, why))
        job.finished.connect(self._remove_done)
        self._remove = job
        job.start()
        return True

    def _remove_done(self) -> None:
        job, self._remove = self._remove, None
        if job is not None:
            job.deleteLater()

    def _job_result(self, result) -> None:
        device = self.get(self._sending_key)
        if device is not None and result.storages:
            device.storages = result.storages
        self.sent.emit(self._sending_key, result)

    def _job_done(self) -> None:
        job, self._send = self._send, None
        if job is not None:
            job.deleteLater()

    # -- eject
    def eject(self, key: str) -> None:
        """Let go of the device so it can be unplugged: stop what is running with it, wait for that to end, close it, and
        take it off the list (it comes back when it is plugged in again)."""
        if self.get(key) is None:
            return
        self._eject_key = key
        self.cancel()
        if self._read is not None:
            self._read.cancel()
        self._finish_eject()

    def _finish_eject(self) -> None:
        if self._send is not None or self._read is not None or self._remove is not None or self._scan is not None:
            QTimer.singleShot(150, self._finish_eject)      # the jobs are winding down: their sessions close the device
            return
        key, device = self._eject_key, self.get(self._eject_key)
        if device is None:
            return
        if device.backend == "fuse":                        # a folder mounted by the desktop: unmount it too
            try:
                subprocess.run(["gio", "mount", "-u", device.route], capture_output=True, timeout=15)
            except (OSError, subprocess.SubprocessError):
                pass
        self._ejected.add(key)
        self.devices = [d for d in self.devices if d.key != key]
        self.changed.emit()
        self.ejected.emit(key, device.label)

    def shutdown(self) -> None:
        self._timer.stop()
        if self._send is not None:
            self._send.cancel()
            self._send.wait(4000)
        if self._read is not None:
            self._read.cancel()
            self._read.wait(4000)
        if self._remove is not None:
            self._remove.wait(4000)
        if self._scan is not None:
            self._scan.wait(4000)
