"""A device that GNOME (gvfs) or another program already mounted: its MTP storage shows up as an ordinary folder, so
songs are simply copied into it. libmtp is refused by such a device, because the mounting program holds it."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

from . import mtp


def _roots() -> list[Path]:
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}") / "gvfs"
    try:
        return [p for p in base.iterdir() if p.name.startswith("mtp:")]
    except OSError:
        return []


def _mount_for(device: mtp.Device) -> Path | None:
    usb = mtp._usb_dir(device.bus, device.devnum)
    serial = mtp._read(usb / "serial") if usb else ""
    for root in _roots():
        name = unquote(root.name)
        if (serial and serial in name) or f"usb:{device.bus:03d},{device.devnum:03d}" in name:
            return root
    return None


def attach(device: mtp.Device) -> bool:
    root = _mount_for(device)
    if root is None:
        return False
    try:
        stores = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return False
    found = []
    for i, store in enumerate(stores):
        try:
            usage = os.statvfs(store)
            capacity, free = usage.f_blocks * usage.f_frsize, usage.f_bavail * usage.f_frsize
        except OSError:
            capacity = free = 0
        found.append(mtp.Storage(i, store.name, capacity, free))
    if not found:
        return False
    device.storages, device.backend, device.route, device.state = found, "fuse", str(root), "ready"
    return True


class Session:
    """The same shape as mtp.Session, over a mounted folder."""

    def __init__(self, device: mtp.Device, wait: bool = True) -> None:
        self.device = device
        self._listing: dict[str, dict[str, mtp.Entry]] = {}

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def _store(self, storage_id: int) -> Path:
        names = sorted(p.name for p in Path(self.device.route).iterdir() if p.is_dir())
        if storage_id >= len(names):
            raise mtp.MtpError("the storage is gone")
        return Path(self.device.route) / names[storage_id]

    def names(self) -> tuple[str, str]:
        return self.device.name, ""

    def storages(self) -> list[mtp.Storage]:
        attach_copy = mtp.Device(self.device.key, self.device.bus, self.device.devnum, self.device.vendor, self.device.product)
        return attach_copy.storages if attach(attach_copy) else list(self.device.storages)

    def children(self, storage_id: int, parent="", refresh: bool = False) -> dict[str, mtp.Entry]:
        where = parent if isinstance(parent, str) and parent else str(self._store(storage_id))
        if where in self._listing and not refresh:
            return self._listing[where]
        found: dict[str, mtp.Entry] = {}
        try:
            for entry in os.scandir(where):
                found[entry.name] = mtp.Entry(0, entry.name, entry.stat().st_size if entry.is_file() else 0, entry.is_dir(), entry.path)
        except OSError:
            pass
        self._listing[where] = found
        return found

    def root(self, storage_id: int) -> str:
        return str(self._store(storage_id))

    def delete(self, storage_id: int, ref: str) -> None:
        try:
            Path(ref).unlink() if Path(ref).is_file() else Path(ref).rmdir()
        except OSError as exc:
            raise mtp.MtpError(str(exc)) from exc

    def folder(self, storage_id: int, parts: list[str]) -> str:
        path = self._store(storage_id).joinpath(*parts)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise mtp.MtpError(str(exc)) from exc
        return str(path)

    def send(self, storage_id: int, parent: str, path: str, name: str,
             progress: Callable[[int, int], bool] | None = None) -> None:
        target = Path(parent) / name
        size = os.path.getsize(path)
        sent = 0
        try:
            with open(path, "rb") as src, open(target, "wb") as dst:
                while True:
                    block = src.read(1 << 20)
                    if not block:
                        break
                    dst.write(block)
                    sent += len(block)
                    if progress is not None and not progress(sent, size):
                        raise mtp.Cancelled(name)
        except mtp.Cancelled:
            target.unlink(missing_ok=True)                 # half a song is worse than none
            raise
        except OSError as exc:
            target.unlink(missing_ok=True)
            raise mtp.MtpError(str(exc)) from exc
        self._listing.setdefault(parent, {})[name] = mtp.Entry(0, name, size, False)
