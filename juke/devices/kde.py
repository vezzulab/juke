"""A device that KDE Plasma already holds: its MTP service (kmtpd, inside kiod6) opens every MTP device the moment it is
plugged in, so libmtp is refused. The same service offers the device to any program over D-Bus, and Juke asks it.

Answers are read with ``busctl`` (JSON), which understands the service's structures; the file itself travels as an open
file descriptor through QtDBus, as KDE's own file manager does it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from typing import Callable

from . import mtp

SERVICE = "org.kde.kmtpd5"
DAEMON = "/modules/kmtpd"
_lock = threading.Lock()


def _run(*args: str, timeout: float = 15.0):
    """``busctl --user --json=short <args>``, parsed; None if the service does not answer."""
    try:
        out = subprocess.run(["busctl", "--user", "--json=short", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def _call(path: str, interface: str, method: str, *strings: str):
    reply = _run("call", SERVICE, path, interface, method, *(("s" * len(strings),) + strings if strings else ()))
    return reply["data"] if reply else None


def _prop(path: str, interface: str, name: str):
    reply = _run("get-property", SERVICE, path, interface, name)
    return reply["data"] if reply else None


def transferring() -> bool:
    return _lock.locked()


def _storage_path(device: mtp.Device, storage_id: int) -> str:
    return f"{device.route}/storage{storage_id}"


def attach(device: mtp.Device) -> bool:
    """If KDE's service holds this device, fill ``device`` in from it and use the service for it. False otherwise."""
    if shutil.which("busctl") is None:
        return False
    listing = _call(DAEMON, "org.kde.kmtp.Daemon", "listDevices")
    usb = mtp._usb_dir(device.bus, device.devnum)
    if not listing or usb is None:
        return False
    for path in listing[0]:
        udi = _prop(path, "org.kde.kmtp.Device", "udi") or ""
        if udi.rstrip("/").rsplit("/", 1)[-1] != usb.name:
            continue
        stores = _call(path, "org.kde.kmtp.Device", "listStorages")
        found = []
        for store in (stores[0] if stores else []):
            capacity = _prop(store, "org.kde.kmtp.Storage", "maxCapacity") or 0
            free = _prop(store, "org.kde.kmtp.Storage", "freeSpaceInBytes") or 0
            name = _prop(store, "org.kde.kmtp.Storage", "description") or ""
            found.append(mtp.Storage(int(store.rsplit("storage", 1)[-1]), name, int(capacity), int(free)))
        device.name = _prop(path, "org.kde.kmtp.Device", "friendlyName") or device.name
        device.storages, device.backend, device.route, device.state = found, "kde", path, "ready"
        return True
    return False


def _send_fd(storage_path: str, fd: int, destination: str) -> int:
    """Hand the open file to the service; it copies it to ``destination`` on the device. 0 means it worked."""
    from PySide6.QtDBus import QDBus, QDBusConnection, QDBusInterface, QDBusMessage, QDBusUnixFileDescriptor

    iface = QDBusInterface(SERVICE, storage_path, "org.kde.kmtp.Storage", QDBusConnection.sessionBus())
    iface.setTimeout(30 * 60 * 1000)                        # a long song over a slow cable is still a song
    reply = iface.call(QDBus.Block, "sendFileFromFileDescriptor", QDBusUnixFileDescriptor(fd), destination)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage or not reply.arguments():
        return -1
    return int(reply.arguments()[0])


class Session:
    """The same shape as mtp.Session, over KDE's service. Folders are paths ("/Music/Artist/Album")."""

    def __init__(self, device: mtp.Device, wait: bool = True) -> None:
        self.device = device
        self._wait = wait
        self._known: set[str] = set()
        self._listing: dict[str, dict[str, mtp.Entry]] = {}

    def __enter__(self) -> "Session":
        if not _lock.acquire(blocking=self._wait):
            raise mtp.MtpError("busy")
        return self

    def __exit__(self, *_exc) -> None:
        _lock.release()

    def names(self) -> tuple[str, str]:
        return self.device.name, ""

    def storages(self) -> list[mtp.Storage]:
        found = []
        for storage in self.device.storages:
            path = _storage_path(self.device, storage.id)
            free = _prop(path, "org.kde.kmtp.Storage", "freeSpaceInBytes")
            found.append(mtp.Storage(storage.id, storage.name, storage.capacity, int(free) if free is not None else storage.free))
        return found

    def children(self, storage_id: int, parent="/", refresh: bool = False) -> dict[str, mtp.Entry]:
        parent = parent if isinstance(parent, str) and parent != mtp.ROOT else "/"
        if parent in self._listing and not refresh:
            return self._listing[parent]
        data = _call(_storage_path(self.device, storage_id), "org.kde.kmtp.Storage", "getFilesAndFolders", parent)
        found: dict[str, mtp.Entry] = {}
        for item_id, _parent, _storage, name, size, _mtime, kind in (data[0] if data else []):
            found[name] = mtp.Entry(item_id, name, int(size), kind == "inode/directory", f"{parent.rstrip('/')}/{name}")
        self._listing[parent] = found
        return found

    def root(self, storage_id: int) -> str:
        return "/"

    def delete(self, storage_id: int, ref: str) -> None:
        code = _call(_storage_path(self.device, storage_id), "org.kde.kmtp.Storage", "deleteObject", ref)
        if not code or code[0] != 0:
            raise mtp.MtpError("could not delete")
        for listing in self._listing.values():
            listing.pop(ref.rsplit("/", 1)[-1], None)

    def folder(self, storage_id: int, parts: list[str]) -> str:
        """The path of the folder at ``parts``; the ones that are missing are created."""
        path, store = "", _storage_path(self.device, storage_id)
        for part in parts:
            path = f"{path}/{part}"
            if path in self._known:
                continue
            found = _call(store, "org.kde.kmtp.Storage", "getFileMetadata", path)
            if not (found and found[0][0]):
                made = _call(store, "org.kde.kmtp.Storage", "createFolder", path)
                if not (made and made[0]):
                    raise mtp.MtpError(f"could not create the folder {part}")
            self._known.add(path)
        return path or "/"

    def send(self, storage_id: int, parent: str, path: str, name: str,
             progress: Callable[[int, int], bool] | None = None) -> None:
        size = os.path.getsize(path)
        if progress is not None and not progress(0, size):
            raise mtp.Cancelled(name)                      # one song is one call: stopping happens between songs
        fd = os.open(path, os.O_RDONLY)
        try:
            code = _send_fd(_storage_path(self.device, storage_id), fd, f"{parent.rstrip('/')}/{name}")
        finally:
            os.close(fd)
        if code != 0:
            raise mtp.MtpError(name)
        self._listing.setdefault(parent, {})[name] = mtp.Entry(0, name, size, False)
        if progress is not None:
            progress(size, size)
