"""Phones and tablets over USB (MTP), spoken through libmtp with ctypes.

No file manager, gvfs or mount is needed: libmtp is bundled in the AppImage. Nothing here touches Qt, so it can be
run and tested on its own. One device is open at a time and only while something is being done with it, so a file
manager or another program is never locked out longer than a transfer lasts.
"""

from __future__ import annotations

import ctypes as C
import ctypes.util
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

ROOT = 0xFFFFFFFF                     # LIBMTP_FILES_AND_FOLDERS_ROOT: listing the top of a storage
FOLDER = 0                            # LIBMTP_FILETYPE_FOLDER
UNKNOWN = 44                          # LIBMTP_FILETYPE_UNKNOWN
FILETYPES = {".wav": 1, ".mp3": 2, ".wma": 3, ".ogg": 4, ".oga": 4, ".opus": 4, ".aac": 30, ".flac": 32, ".m4a": 34,
             ".mp4": 6}
SYSFS = Path("/sys/bus/usb/devices")
_lock = threading.Lock()              # libusb does not like two sessions at once


class MtpError(Exception):
    """The device said no (or went away)."""


class Cancelled(MtpError):
    pass


@dataclass(slots=True)
class Storage:
    id: int
    name: str
    capacity: int
    free: int
    writable: bool = True


@dataclass(slots=True)
class Device:
    key: str                          # "bus:devnum": changes whenever the device is replugged or changes USB mode
    bus: int
    devnum: int
    vendor: str
    product: str
    name: str = ""
    # ready: open and browsable | waiting: plugged in, but its USB mode is "charging only" (no MTP interface yet)
    # busy: MTP is offered but Juke could not open it (a file manager or another program holds it)
    state: str = "waiting"
    storages: list[Storage] = field(default_factory=list)
    # who talks to it: libmtp itself, or "kde" (Plasma's MTP service) / "fuse" (a mount, e.g. gvfs's), when that program
    # already holds the device and libmtp is refused
    backend: str = "libmtp"
    route: str = ""

    @property
    def label(self) -> str:
        return self.name or f"{self.vendor} {self.product}".strip()


@dataclass(slots=True)
class Entry:
    id: int
    name: str
    size: int
    is_folder: bool
    ref: object = None                # what to pass back to reach it: an object id (libmtp) or a path (the others)


# -- libmtp -----------------------------------------------------------------------------------------------------------
class _Entry(C.Structure):
    _fields_ = [("vendor", C.c_char_p), ("vendor_id", C.c_uint16), ("product", C.c_char_p), ("product_id", C.c_uint16),
                ("flags", C.c_uint32)]


class _Raw(C.Structure):
    _fields_ = [("entry", _Entry), ("bus_location", C.c_uint32), ("devnum", C.c_uint8)]


class _Storage(C.Structure):
    pass


_Storage._fields_ = [("id", C.c_uint32), ("StorageType", C.c_uint16), ("FilesystemType", C.c_uint16),
                     ("AccessCapability", C.c_uint16), ("MaxCapacity", C.c_uint64), ("FreeSpaceInBytes", C.c_uint64),
                     ("FreeSpaceInObjects", C.c_uint64), ("StorageDescription", C.c_char_p),
                     ("VolumeIdentifier", C.c_char_p), ("next", C.POINTER(_Storage)), ("prev", C.POINTER(_Storage))]


class _Dev(C.Structure):
    _fields_ = [("object_bitsize", C.c_uint8), ("params", C.c_void_p), ("usbinfo", C.c_void_p),
                ("storage", C.POINTER(_Storage))]


class _File(C.Structure):
    pass


_File._fields_ = [("item_id", C.c_uint32), ("parent_id", C.c_uint32), ("storage_id", C.c_uint32),
                  ("filename", C.c_void_p), ("filesize", C.c_uint64), ("mtime", C.c_long), ("filetype", C.c_int),
                  ("next", C.POINTER(_File))]
_PROGRESS = C.CFUNCTYPE(C.c_int, C.c_uint64, C.c_uint64, C.c_void_p)

_libmtp = None
_libc = C.CDLL(None)
_libc.strdup.restype = C.c_void_p
_libc.strdup.argtypes = [C.c_char_p]
_libc.free.argtypes = [C.c_void_p]


def _load():
    """libmtp, or None when the system has none (the AppImage carries its own)."""
    global _libmtp
    if _libmtp is not None:
        return _libmtp or None
    lib = None
    for name in ("libmtp.so.9", ctypes.util.find_library("mtp")):
        try:
            lib = C.CDLL(name) if name else None
        except OSError:
            lib = None
        if lib is not None:
            break
    if lib is None:
        _libmtp = False
        return None
    lib.LIBMTP_Init()
    lib.LIBMTP_Detect_Raw_Devices.argtypes = [C.POINTER(C.POINTER(_Raw)), C.POINTER(C.c_int)]
    lib.LIBMTP_Open_Raw_Device_Uncached.restype = C.POINTER(_Dev)
    lib.LIBMTP_Open_Raw_Device_Uncached.argtypes = [C.POINTER(_Raw)]
    lib.LIBMTP_Release_Device.argtypes = [C.POINTER(_Dev)]
    for text in ("Friendlyname", "Modelname", "Manufacturername"):
        getattr(lib, f"LIBMTP_Get_{text}").restype = C.c_void_p
        getattr(lib, f"LIBMTP_Get_{text}").argtypes = [C.POINTER(_Dev)]
    lib.LIBMTP_Get_Storage.argtypes = [C.POINTER(_Dev), C.c_int]
    lib.LIBMTP_Get_Files_And_Folders.restype = C.POINTER(_File)
    lib.LIBMTP_Get_Files_And_Folders.argtypes = [C.POINTER(_Dev), C.c_uint32, C.c_uint32]
    lib.LIBMTP_destroy_file_t.argtypes = [C.POINTER(_File)]
    lib.LIBMTP_new_file_t.restype = C.POINTER(_File)
    lib.LIBMTP_Create_Folder.restype = C.c_uint32
    lib.LIBMTP_Create_Folder.argtypes = [C.POINTER(_Dev), C.c_char_p, C.c_uint32, C.c_uint32]
    lib.LIBMTP_Send_File_From_File.argtypes = [C.POINTER(_Dev), C.c_char_p, C.POINTER(_File), _PROGRESS, C.c_void_p]
    lib.LIBMTP_Clear_Errorstack.argtypes = [C.POINTER(_Dev)]
    lib.LIBMTP_Delete_Object.argtypes = [C.POINTER(_Dev), C.c_uint32]
    _libmtp = lib
    return lib


def available() -> bool:
    return _load() is not None


def _text(pointer: int | None) -> str:
    if not pointer:
        return ""
    try:
        return C.string_at(pointer).decode("utf-8", "replace")
    finally:
        _libc.free(pointer)


def _raw_devices(lib) -> list[_Raw]:
    """Copies of libmtp's list of the MTP-capable devices that are plugged in (it is freed right away)."""
    raw, count = C.POINTER(_Raw)(), C.c_int()
    if lib.LIBMTP_Detect_Raw_Devices(C.byref(raw), C.byref(count)) != 0 or not count.value:
        return []
    found = []
    for i in range(count.value):
        copy = _Raw()
        C.memmove(C.byref(copy), C.byref(raw[i]), C.sizeof(_Raw))
        found.append(copy)
    _libc.free(C.cast(raw, C.c_void_p))
    return found


# -- USB, as the kernel shows it (no libusb, no opening) -------------------------------------------------------------
def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def usb_signature() -> tuple:
    """What is plugged in, in a form that changes whenever a device arrives, leaves, or re-enumerates in another USB
    mode (choosing "File transfer" on a phone does exactly that). A few tiny reads: cheap enough to poll."""
    try:
        return tuple(sorted((p.name, _read(p / "devnum")) for p in SYSFS.iterdir() if ":" not in p.name))
    except OSError:
        return ()


def _usb_dir(bus: int, devnum: int) -> Path | None:
    try:
        for path in SYSFS.iterdir():
            if ":" not in path.name and _read(path / "busnum") == str(bus) and _read(path / "devnum") == str(devnum):
                return path
    except OSError:
        pass
    return None


def offers_mtp(bus: int, devnum: int) -> bool:
    """Whether the device shows an MTP/PTP interface right now. A phone set to "charging only" does not."""
    path = _usb_dir(bus, devnum)
    if path is None:
        return True                       # cannot tell: let opening it decide
    for iface in path.glob(f"{path.name}:*"):
        if _read(iface / "bInterfaceClass") == "06" and _read(iface / "bInterfaceSubClass") == "01":
            return True                   # PTP
        if "MTP" in _read(iface / "interface").upper():
            return True
    return False


# -- one open device ---------------------------------------------------------------------------------------------------
class Session:
    """``with Session(device) as s:`` opens the device (waiting its turn) and closes it on the way out."""

    def __init__(self, device: Device, wait: bool = True) -> None:
        self.device = device
        self._wait = wait
        self._dev = None
        self._lib = _load()
        self._listing: dict[int, dict[str, Entry]] = {}

    def __enter__(self) -> "Session":
        if self._lib is None:
            raise MtpError("libmtp is not installed")
        if not _lock.acquire(blocking=self._wait):
            raise MtpError("busy")
        try:
            match = next((r for r in _raw_devices(self._lib)
                          if (r.bus_location, r.devnum) == (self.device.bus, self.device.devnum)), None)
            if match is None:
                raise MtpError("the device is gone")
            self._raw = match
            self._dev = self._lib.LIBMTP_Open_Raw_Device_Uncached(C.byref(self._raw))
            if not self._dev:
                raise MtpError("could not open the device")
        except BaseException:
            _lock.release()
            raise
        return self

    def __exit__(self, *_exc) -> None:
        try:
            if self._dev:
                self._lib.LIBMTP_Release_Device(self._dev)
        finally:
            self._dev = None
            _lock.release()

    # -- what it is
    def names(self) -> tuple[str, str]:
        lib, dev = self._lib, self._dev
        friendly = _text(lib.LIBMTP_Get_Friendlyname(dev))
        model = _text(lib.LIBMTP_Get_Modelname(dev))
        maker = _text(lib.LIBMTP_Get_Manufacturername(dev))
        return friendly or model or maker, model

    def storages(self) -> list[Storage]:
        found = []
        if self._lib.LIBMTP_Get_Storage(self._dev, 0) != 0:
            return found
        node = self._dev.contents.storage
        while node:
            s = node.contents
            name = (s.StorageDescription or b"").decode("utf-8", "replace") or (s.VolumeIdentifier or b"").decode("utf-8", "replace")
            found.append(Storage(s.id, name, s.MaxCapacity, s.FreeSpaceInBytes, writable=s.AccessCapability == 0))   # 1 and 2 are read-only
            node = s.next
        return found

    # -- what is on it
    def children(self, storage_id: int, parent: int = ROOT, refresh: bool = False) -> dict[str, Entry]:
        """The files and folders directly inside ``parent`` (ROOT = the top of the storage), by name."""
        if parent in self._listing and not refresh:
            return self._listing[parent]
        found: dict[str, Entry] = {}
        node = self._lib.LIBMTP_Get_Files_And_Folders(self._dev, storage_id, parent)
        while node:
            f = node.contents
            following = f.next
            name = C.string_at(f.filename).decode("utf-8", "replace") if f.filename else ""
            found[name] = Entry(f.item_id, name, f.filesize, f.filetype == FOLDER, f.item_id)
            self._lib.LIBMTP_destroy_file_t(node)
            node = following
        self._listing[parent] = found
        return found

    def root(self, storage_id: int):
        return ROOT

    def delete(self, storage_id: int, ref) -> None:
        if self._lib.LIBMTP_Delete_Object(self._dev, int(ref)) != 0:
            self._lib.LIBMTP_Clear_Errorstack(self._dev)
            raise MtpError("could not delete")

    def folder(self, storage_id: int, parts: list[str]) -> int:
        """The id of the folder at ``parts`` from the top of the storage; missing ones are created."""
        parent = ROOT
        for part in parts:
            entries = self.children(storage_id, parent)
            found = entries.get(part)
            if found is not None and found.is_folder:
                parent = found.id
                continue
            made = self._lib.LIBMTP_Create_Folder(self._dev, C.create_string_buffer(part.encode("utf-8")),
                                                  0 if parent == ROOT else parent, storage_id)
            if not made:
                self._lib.LIBMTP_Clear_Errorstack(self._dev)
                raise MtpError(f"could not create the folder {part}")
            entries[part] = Entry(made, part, 0, True)
            parent = made
        return parent

    def send(self, storage_id: int, parent: int, path: str, name: str,
             progress: Callable[[int, int], bool] | None = None) -> None:
        """Copy the local file ``path`` into ``parent`` under ``name``. ``progress(sent, total)`` returns False to stop."""
        lib = self._lib
        meta = lib.LIBMTP_new_file_t()
        meta.contents.filename = _libc.strdup(name.encode("utf-8"))
        meta.contents.filesize = os.path.getsize(path)
        meta.contents.filetype = FILETYPES.get(os.path.splitext(name)[1].lower(), UNKNOWN)
        meta.contents.parent_id = 0 if parent == ROOT else parent
        meta.contents.storage_id = storage_id
        stopped = False

        def tick(sent, total, _data):
            nonlocal stopped
            if progress is not None and not progress(int(sent), int(total)):
                stopped = True
                return 1
            return 0

        callback = _PROGRESS(tick)                # kept alive for the whole call
        try:
            status = lib.LIBMTP_Send_File_From_File(self._dev, os.fsencode(path), meta, callback, None)
            if status != 0:
                lib.LIBMTP_Clear_Errorstack(self._dev)
                if stopped:
                    raise Cancelled(name)
                raise MtpError(name)
            self._listing.setdefault(parent, {})[name] = Entry(meta.contents.item_id, name, meta.contents.filesize, False)
        finally:
            lib.LIBMTP_destroy_file_t(meta)


# -- finding devices -----------------------------------------------------------------------------------------------------
def _describe(lib, raw: _Raw) -> Device:
    vendor = (raw.entry.vendor or b"").decode("utf-8", "replace")
    product = re.sub(r"\s*\(MTP\)\s*$", "", (raw.entry.product or b"").decode("utf-8", "replace"))
    device = Device(f"{raw.bus_location}:{raw.devnum}", raw.bus_location, raw.devnum, vendor, product)
    if not offers_mtp(device.bus, device.devnum):
        return device                                        # "waiting": Juke tells the person what to do on the phone
    from . import fuse, kde

    if kde.attach(device) or fuse.attach(device):            # the desktop already holds it: use what the desktop offers
        return device
    device.state = "busy"
    try:
        with Session(device, wait=False) as session:
            device.name, _model = session.names()
            device.storages = session.storages()
            device.state = "ready"
    except MtpError as exc:
        if str(exc) == "busy":
            device.state = "busy"
    return device


def open_session(device: Device, wait: bool = True):
    """The session that suits the way this device is reached."""
    if device.backend == "kde":
        from . import kde
        return kde.Session(device, wait)
    if device.backend == "fuse":
        from . import fuse
        return fuse.Session(device, wait)
    return Session(device, wait)


def scan() -> list[Device] | None:
    """The devices plugged in now, with what can be read of each. None when a transfer is using libmtp (keep what you
    had) or when there is no libmtp at all."""
    lib = _load()
    if lib is None:
        return None
    from . import kde

    if kde.transferring() or not _lock.acquire(blocking=False):
        return None
    try:
        raws = _raw_devices(lib)
    finally:
        _lock.release()
    found = []
    for raw in raws:
        try:
            found.append(_describe(lib, raw))
        except Exception:                                    # a device that misbehaves must not hide the others
            continue
    return found


def iter_audio(paths: list[str], extensions: set[str] | frozenset[str]) -> Iterator[str]:
    """The audio files among ``paths``, looking inside folders."""
    for path in paths:
        if os.path.isdir(path):
            for base, dirs, files in os.walk(path):
                dirs.sort()
                for name in sorted(files):
                    if os.path.splitext(name)[1].lower() in extensions:
                        yield os.path.join(base, name)
        elif os.path.splitext(path)[1].lower() in extensions:
            yield path
