import os
import unittest
from pathlib import Path

from . import helpers  # noqa: F401  (sets XDG env first)

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtWidgets import QApplication, QLabel

import juke.gui.main_window as mw
from juke.devices import fuse, kde, mtp, transfer
from juke.gui.components.sidebar import MIME_FOLDER
from juke.i18n import translator

from .test_folders_gui import drag_through, tracks_mime
from .test_gui import make_window, pump


def make_device(key="1:5", state="ready", vendor="Samsung", product="Galaxy models", name="Galaxy Tab"):
    bus, num = key.split(":")
    return mtp.Device(key, int(bus), int(num), vendor, product, name, state,
                      [mtp.Storage(65537, "Internal storage", 64 << 30, 20 << 30)] if state == "ready" else [])


class FakeSession:
    """Stands in for a phone: folders and files live in dicts, and every send is recorded."""

    instances: list = []
    existing: dict = {}
    fail_names: set = set()
    stop_after: int | None = None
    storage_list: list = []

    def __init__(self, device, wait=True):
        self.sent, self.made, self.used, self.covers = [], [], [], []
        self.tree = {mtp.ROOT: {}}
        self.next_id = 100
        FakeSession.instances.append(self)
        for parts in FakeSession.existing:               # what the phone already holds is there before anything is sent
            self.folder(1, list(parts))
        self.made = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def storages(self):
        return FakeSession.storage_list or [mtp.Storage(1, "Internal storage", 100, 50)]

    def children(self, storage, parent=mtp.ROOT, refresh=False):
        return self.tree.setdefault(parent, {})

    def folder(self, storage, parts):
        parent = mtp.ROOT
        for part in parts:
            entries = self.tree.setdefault(parent, {})
            if part not in entries:
                self.next_id += 1
                entries[part] = mtp.Entry(self.next_id, part, 0, True, self.next_id)
                self.made.append(part)
            parent = entries[part].id
        for name, size in FakeSession.existing.get(tuple(parts), {}).items():
            self.tree.setdefault(parent, {})[name] = mtp.Entry(1, name, size, False, 1)
        return parent

    def send(self, storage, parent, path, name, progress=None):
        if name in FakeSession.fail_names:
            raise mtp.MtpError(name)
        if FakeSession.stop_after is not None and len(self.sent) >= FakeSession.stop_after:
            raise mtp.Cancelled(name)
        if progress:
            progress(5, 10)
            progress(10, 10)
        from juke.db.indexer import embedded_cover

        self.used.append(storage)
        self.covers.append(embedded_cover(path) is not None)         # what was sent, looked at before its temporary copy goes
        self.sent.append((parent, name, os.path.getsize(path)))
        self.tree.setdefault(parent, {})[name] = mtp.Entry(2, name, 1, False)


class TransferTests(unittest.TestCase):
    def setUp(self):
        self._orig = mtp.Session
        mtp.Session = FakeSession
        FakeSession.instances, FakeSession.existing, FakeSession.fail_names, FakeSession.stop_after = [], {}, set(), None
        FakeSession.storage_list = []
        self.dir = Path(helpers.ROOT) / f"send-{self._testMethodName}"
        self.dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        mtp.Session = self._orig

    def song(self, name, size=10):
        path = self.dir / name
        path.write_bytes(b"x" * size)
        return str(path)

    def run_send(self, items, cancelled=lambda: False):
        events = []
        result = transfer.send(make_device(), items, lambda *a: events.append(a), cancelled)
        return result, events

    def test_songs_go_to_music_and_the_artists_folder(self):
        item = transfer.Item("a.mp3", "The Artist", "The Album", path=self.song("a.mp3"))
        result, events = self.run_send([item])
        session = FakeSession.instances[0]
        self.assertEqual((result.sent, result.skipped, result.failed), (1, 0, []))
        self.assertEqual(session.made, ["Music", "The Artist"])                # one folder deep: no album folder
        self.assertEqual(session.sent[0][1], "a.mp3")
        self.assertEqual(events[-1][:2], (1, 1))                     # the last call says everything is done
        self.assertEqual(len(result.storages), 1)

    def test_names_the_phone_would_refuse_are_cleaned(self):
        self.assertEqual(transfer.clean('AC/DC: "Live"?', "x"), "AC_DC_ _Live_")
        self.assertEqual(transfer.clean("...", "Unknown"), "Unknown")
        self.assertEqual(transfer.clean("a" * 300, "x"), "a" * 120)
        item = transfer.Item("b.mp3", "AC/DC", "", path=self.song("b.mp3"))
        self.run_send([item])
        self.assertEqual(FakeSession.instances[0].made, ["Music", "AC_DC"])

    def test_a_folder_is_one_folder_on_the_phone_whatever_the_songs_say(self):
        songs = [transfer.Item(f"{i}.mp3", f"Artist {i}", f"Album {i}", path=self.song(f"f{i}.mp3"), folder="Sin Fronteras") for i in range(3)]
        self.run_send(songs)
        session = FakeSession.instances[0]
        self.assertEqual(session.made, ["Music", "Sin Fronteras"])            # not a folder per artist, not one per album
        self.assertEqual(len(session.sent), 3)
        self.assertEqual(len({parent for parent, _n, _s in session.sent}), 1)

    def test_an_album_named_like_its_artist_never_makes_a_folder_inside_a_folder(self):
        item = transfer.Item("a.mp3", "Sandy Reyes", "Sandy Reyes", path=self.song("a.mp3"))
        self.run_send([item])
        self.assertEqual(FakeSession.instances[0].made, ["Music", "Sandy Reyes"])

    def test_a_song_sent_by_the_old_layout_is_not_sent_again(self):
        FakeSession.existing = {("Music", "Sandy Reyes"): {}, ("Music", "Sandy Reyes", "Sandy Reyes"): {"a.mp3": 10}}
        item = transfer.Item("a.mp3", "Sandy Reyes", "Sandy Reyes", path=self.song("a.mp3", 10))
        result, _ = self.run_send([item])
        self.assertEqual((result.sent, result.skipped), (0, 1))

    def test_a_song_left_by_the_album_layout_is_not_sent_again_either(self):
        FakeSession.existing = {("Music", "A"): {}, ("Music", "A", "B"): {"a.mp3": 10}}
        item = transfer.Item("a.mp3", "A", "B", path=self.song("a.mp3", 10))
        result, _ = self.run_send([item])
        self.assertEqual((result.sent, result.skipped), (0, 1))

    def test_a_song_the_phone_already_has_is_skipped(self):
        FakeSession.existing = {("Music", "A"): {"c.mp3": 10}}
        same = transfer.Item("c.mp3", "A", "B", path=self.song("c.mp3", 10))
        other_size = transfer.Item("c.mp3", "A", "B", path=self.song("c2.mp3", 12))
        other_size.name = "c.mp3"
        result, _ = self.run_send([same, other_size])
        self.assertEqual((result.sent, result.skipped), (1, 1))      # same size: skipped; a different file of that name: sent

    def test_a_failure_does_not_stop_the_rest_but_three_in_a_row_do(self):
        FakeSession.fail_names = {"bad.mp3"}
        items = [transfer.Item("bad.mp3", "A", "B", path=self.song("bad.mp3")),
                 transfer.Item("ok.mp3", "A", "B", path=self.song("ok.mp3"))]
        result, _ = self.run_send(items)
        self.assertEqual((result.sent, result.failed), (1, ["bad.mp3"]))
        FakeSession.fail_names = {f"{i}.mp3" for i in range(6)}
        many = [transfer.Item(f"{i}.mp3", "A", "B", path=self.song(f"{i}.mp3")) for i in range(6)]
        result, _ = self.run_send(many)
        self.assertEqual((result.sent, len(result.failed)), (0, 6))  # gave up after three, and counted the rest as failed

    def test_stopping_keeps_what_was_sent(self):
        items = [transfer.Item(f"{i}.mp3", "A", "B", path=self.song(f"s{i}.mp3")) for i in range(4)]
        flag = {"n": 0}

        def cancelled():
            flag["n"] += 1
            return flag["n"] > 3
        result, _ = self.run_send(items, cancelled)
        self.assertTrue(result.cancelled)
        self.assertLess(result.sent, 4)

    def two_storages(self):
        FakeSession.storage_list = [mtp.Storage(1, "Internal storage", 100, 50), mtp.Storage(2, "SD card", 900, 800),
                                    mtp.Storage(3, "Locked", 10, 1, writable=False)]

    def test_songs_go_to_the_storage_that_was_chosen(self):
        self.two_storages()
        item = transfer.Item("a.mp3", "A", "B", path=self.song("a.mp3"))
        result = transfer.send(make_device(), [item], lambda *a: None, lambda: False, storage_id=2)
        self.assertEqual((FakeSession.instances[0].used, result.storage), ([2], "SD card"))

    def test_without_a_choice_the_first_writable_storage_is_used(self):
        self.two_storages()
        FakeSession.storage_list.insert(0, mtp.Storage(9, "Read only", 10, 1, writable=False))
        item = transfer.Item("a.mp3", "A", "B", path=self.song("a.mp3"))
        result = transfer.send(make_device(), [item], lambda *a: None, lambda: False)
        self.assertEqual((FakeSession.instances[0].used, result.storage), ([1], "Internal storage"))

    def test_a_card_that_was_taken_out_falls_back_to_the_internal_memory(self):
        self.two_storages()
        item = transfer.Item("a.mp3", "A", "B", path=self.song("a.mp3"))
        transfer.send(make_device(), [item], lambda *a: None, lambda: False, storage_id=77)
        self.assertEqual(FakeSession.instances[0].used, [1])

    def test_audio_files_are_found_inside_folders(self):
        (self.dir / "sub").mkdir(exist_ok=True)
        for name in ("one.mp3", "sub/two.FLAC", "sub/readme.txt"):
            (self.dir / name).write_bytes(b"x")
        found = [os.path.relpath(p, self.dir) for p in mtp.iter_audio([str(self.dir)], {".mp3", ".flac"})]
        self.assertEqual(sorted(found), ["one.mp3", "sub/two.FLAC"])


class UsbTests(unittest.TestCase):
    def setUp(self):
        self._orig = mtp.SYSFS
        self.sysfs = Path(helpers.ROOT) / f"sysfs-{self._testMethodName}"
        self.sysfs.mkdir(parents=True, exist_ok=True)
        mtp.SYSFS = self.sysfs

    def tearDown(self):
        mtp.SYSFS = self._orig

    def plug(self, name, bus, num, interfaces):
        base = self.sysfs / name
        base.mkdir(exist_ok=True)
        (base / "busnum").write_text(f"{bus}\n")
        (base / "devnum").write_text(f"{num}\n")
        for i, (cls, sub, label) in enumerate(interfaces):
            iface = base / f"{name}:1.{i}"          # like the kernel: the interfaces sit inside the device
            iface.mkdir(exist_ok=True)
            (iface / "bInterfaceClass").write_text(cls + "\n")
            (iface / "bInterfaceSubClass").write_text(sub + "\n")
            if label:
                (iface / "interface").write_text(label + "\n")

    def test_a_phone_set_to_charging_only_offers_no_mtp(self):
        self.plug("1-1", 1, 2, [("ff", "42", "ADB Interface")])             # what the tablet showed on the laptop
        self.assertFalse(mtp.offers_mtp(1, 2))

    def test_file_transfer_mode_is_recognised(self):
        self.plug("1-1", 1, 3, [("ff", "ff", "MTP"), ("ff", "42", "ADB Interface")])
        self.assertTrue(mtp.offers_mtp(1, 3))
        self.plug("1-2", 1, 4, [("06", "01", "")])                          # a camera-style PTP interface
        self.assertTrue(mtp.offers_mtp(1, 4))

    def test_the_signature_changes_when_the_usb_mode_changes(self):
        self.plug("1-1", 1, 2, [("ff", "42", "ADB Interface")])
        before = mtp.usb_signature()
        self.assertEqual(mtp.usb_signature(), before)
        (self.sysfs / "1-1" / "devnum").write_text("9\n")                   # the kernel re-enumerates it
        self.assertNotEqual(mtp.usb_signature(), before)


def jpeg(color="red", side=64):
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage

    image = QImage(side, side, QImage.Format_RGB32)
    image.fill(QColor(color))
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "JPEG", 90)
    return bytes(buffer.data())


class CoverTests(unittest.TestCase):
    """A song reaches the phone with its picture inside it, because that is where the phone's player looks for it."""

    def setUp(self):
        self._orig = (mtp.Session, transfer.urllib.request.urlopen)
        mtp.Session = FakeSession
        FakeSession.instances, FakeSession.existing, FakeSession.fail_names, FakeSession.stop_after = [], {}, set(), None
        FakeSession.storage_list = []
        self.dir = Path(helpers.ROOT) / f"cover-{self._testMethodName}"
        self.dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        mtp.Session, transfer.urllib.request.urlopen = self._orig

    def wav(self, name="s.wav"):
        from .test_core import write_wav

        path = self.dir / name
        write_wav(path, 0.2)
        return path

    def send(self, item):
        return transfer.send(make_device(), [item], lambda *a: None, lambda: False)

    def library_cover(self, key="k1"):
        from juke.db import indexer

        path = indexer.cover_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg())
        return key

    def test_the_librarys_cover_goes_inside_a_copy_and_the_original_is_left_alone(self):
        from juke.db.indexer import embedded_cover

        song = self.wav()
        before = song.read_bytes()
        result = self.send(transfer.Item("s.wav", "A", "B", path=str(song), cover_key=self.library_cover()))
        self.assertEqual((result.sent, FakeSession.instances[0].covers), (1, [True]))
        self.assertEqual(song.read_bytes(), before)                      # never touched
        self.assertIsNone(embedded_cover(str(song)))

    def test_a_song_that_already_has_its_cover_is_sent_as_it_is(self):
        from juke.db.indexer import write_cover

        song = self.wav("has.wav")
        write_cover(song, jpeg("blue"))
        size = song.stat().st_size
        self.send(transfer.Item("has.wav", "A", "B", path=str(song), cover_key=self.library_cover("other")))
        self.assertEqual(FakeSession.instances[0].sent[0][2], size)      # the very file, not a copy with another picture

    def test_a_picture_next_to_the_file_is_used_when_the_library_has_none(self):
        song = self.wav("nx.wav")
        (self.dir / "folder.jpg").write_bytes(jpeg("green"))
        self.send(transfer.Item("nx.wav", "A", "B", path=str(song)))
        self.assertEqual(FakeSession.instances[0].covers, [True])

    def test_no_picture_anywhere_sends_the_song_without_one(self):
        song = self.wav("plain.wav")
        result = self.send(transfer.Item("plain.wav", "A", "B", path=str(song)))
        self.assertEqual((result.sent, result.failed, FakeSession.instances[0].covers), (1, [], [False]))

    def test_a_file_that_cannot_take_a_picture_is_still_sent(self):
        song = self.dir / "odd.mp3"
        song.write_bytes(b"not really audio")
        result = self.send(transfer.Item("odd.mp3", "A", "B", path=str(song), cover_key=self.library_cover("odd")))
        self.assertEqual((result.sent, result.failed), (1, []))

    def test_a_song_from_the_server_gets_the_servers_cover(self):
        wav = self.wav("server.wav").read_bytes()
        art = jpeg("purple")

        class Response:
            def __init__(self, body, kind):
                self.body, self.headers = body, {"Content-Type": kind, "Content-Length": str(len(body))}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return None

            def read(self, n=-1):
                chunk, self.body = (self.body, b"") if n < 0 else (self.body[:n], self.body[n:])
                return chunk

        asked = []

        def fake(request, timeout=0):
            asked.append(request.full_url)
            return Response(art, "image/jpeg") if "getCoverArt" in request.full_url else Response(wav, "audio/wav")

        transfer.urllib.request.urlopen = fake
        item = transfer.Item("01 Song", "A", "B", url="http://server/rest/download.view?id=1", cover_url="http://server/rest/getCoverArt.view?id=c")
        result = self.send(item)
        self.assertEqual((result.sent, result.failed), (1, []))
        session = FakeSession.instances[0]
        self.assertEqual((session.covers, session.sent[0][1]), ([True], "01 Song.wav"))
        self.assertEqual(len(asked), 2)

    def test_the_extension_is_read_from_whatever_form_the_server_names_the_file_in(self):
        for header, kind, want in (
            ('attachment; filename="Bandolera.mp3"', "", ".mp3"),
            ('attachment; filename==?UTF-8?Q?Bandolera.mp3?=', "audio/mpeg", ".mp3"),            # what Airsonic sends
            ('attachment; filename="=?UTF-8?Q?Ni=C3=B1a.flac?="', "", ".flac"),
            ("attachment; filename*=UTF-8''Ni%C3%B1a.m4a", "", ".m4a"),
            ('attachment; filename="a.MP3"; filename*=UTF-8\'\'a.MP3', "", ".mp3"),
            ("", "audio/flac", ".flac"),
            ('attachment; filename="weird.mp3?="', "audio/ogg", ".ogg"),                          # not a real extension: the kind wins
            ("", "", ".mp3"),
        ):
            self.assertEqual(transfer.extension(header, kind), want, header)

    def test_a_song_the_phone_has_with_its_cover_inside_is_not_sent_again(self):
        song = self.wav("again.wav")
        FakeSession.existing = {("Music", "A"): {"again.wav": song.stat().st_size + 5000}}     # bigger: the cover is in it
        result = self.send(transfer.Item("again.wav", "A", "B", path=str(song)))
        self.assertEqual((result.sent, result.skipped), (0, 1))


class KdeTests(unittest.TestCase):
    """KDE's own MTP service, with its D-Bus answers replaced by what it said to the real tablet."""

    def setUp(self):
        self._orig = (kde._call, kde._prop, kde._send_fd, mtp._usb_dir, kde.shutil.which)
        self.calls, self.sent = [], []
        self.tree = {"/": [[3, 0, 65537, "Music", 0, 1, "inode/directory"]]}
        kde.shutil.which = lambda name: "/usr/bin/busctl"
        mtp._usb_dir = lambda bus, num: Path("/sys/bus/usb/devices/1-1")
        props = {("/modules/kmtpd/device0", "udi"): "/org/kde/solid/udev/sys/devices/pci0000:00/usb1/1-1",
                 ("/modules/kmtpd/device0", "friendlyName"): "SM-T820",
                 ("/modules/kmtpd/device0/storage0", "description"): "Internal shared storage",
                 ("/modules/kmtpd/device0/storage0", "maxCapacity"): 25680748544,
                 ("/modules/kmtpd/device0/storage0", "freeSpaceInBytes"): 24201736192}
        kde._prop = lambda path, interface, name: props.get((path, name))

        def call(path, interface, method, *args):
            self.calls.append((method, args))
            if method == "listDevices":
                return [["/modules/kmtpd/device0"]]
            if method == "listStorages":
                return [["/modules/kmtpd/device0/storage0"]]
            if method == "getFilesAndFolders":
                return [self.tree.get(args[0], []), 0]
            if method == "getFileMetadata":
                hit = next((e for e in self.tree.get(args[0].rsplit("/", 1)[0] or "/", []) if e[3] == args[0].rsplit("/", 1)[1]), None)
                return [hit or [0, 0, 0, "", 0, 0, ""]]
            if method == "createFolder":
                parent, name = (args[0].rsplit("/", 1)[0] or "/"), args[0].rsplit("/", 1)[1]
                self.tree.setdefault(parent, []).append([50 + len(self.calls), 0, 65537, name, 0, 1, "inode/directory"])
                return [50 + len(self.calls)]
            return None
        kde._call = call
        kde._send_fd = lambda storage, fd, destination: self.sent.append((storage, destination, os.read(fd, 100))) or 0

    def tearDown(self):
        kde._call, kde._prop, kde._send_fd, mtp._usb_dir, kde.shutil.which = self._orig

    def device(self):
        return mtp.Device("1:5", 1, 5, "Samsung", "Galaxy models")

    def test_a_device_held_by_kde_is_taken_from_kde(self):
        d = self.device()
        self.assertTrue(kde.attach(d))
        self.assertEqual((d.state, d.backend, d.name, d.route), ("ready", "kde", "SM-T820", "/modules/kmtpd/device0"))
        self.assertEqual([(s.id, s.name, s.free) for s in d.storages], [(0, "Internal shared storage", 24201736192)])

    def test_another_usb_device_is_not_claimed_by_it(self):
        mtp._usb_dir = lambda bus, num: Path("/sys/bus/usb/devices/3-2")
        self.assertFalse(kde.attach(self.device()))

    def test_songs_are_sent_through_the_service_into_music_and_one_folder(self):
        d = self.device()
        kde.attach(d)
        song = Path(helpers.ROOT) / "kde-song.mp3"
        song.write_bytes(b"audio")
        item = transfer.Item("kde-song.mp3", "The Artist", "The Album", path=str(song))
        result = transfer.send(d, [item, item], lambda *a: None, lambda: False)
        self.assertEqual((result.sent, result.skipped, result.failed), (1, 1, []))      # the second is already there
        self.assertEqual(self.sent, [("/modules/kmtpd/device0/storage0", "/Music/The Artist/kde-song.mp3", b"audio")])
        made = [a[0] for m, a in self.calls if m == "createFolder"]
        self.assertEqual(made, ["/Music/The Artist"])                                   # Music existed; the artist's folder did not

    def test_a_refusal_from_the_service_is_a_failed_song(self):
        d = self.device()
        kde.attach(d)
        kde._send_fd = lambda storage, fd, destination: 5
        song = Path(helpers.ROOT) / "kde-bad.mp3"
        song.write_bytes(b"x")
        result = transfer.send(d, [transfer.Item("kde-bad.mp3", "A", "B", path=str(song))], lambda *a: None, lambda: False)
        self.assertEqual((result.sent, result.failed), (0, ["kde-bad.mp3"]))

    def test_the_scan_prefers_what_the_desktop_offers_over_a_refused_libmtp(self):
        raw = mtp._Raw()
        raw.entry.vendor, raw.entry.product = b"Samsung", b"Galaxy models (MTP)"
        raw.bus_location, raw.devnum = 1, 5
        orig = mtp.offers_mtp
        mtp.offers_mtp = lambda bus, num: True
        try:
            d = mtp._describe(None, raw)
        finally:
            mtp.offers_mtp = orig
        self.assertEqual((d.state, d.backend, d.label), ("ready", "kde", "SM-T820"))


class FuseTests(unittest.TestCase):
    """A device that gvfs already mounted as a folder."""

    def setUp(self):
        self.runtime = Path(helpers.ROOT) / f"run-{self._testMethodName}"
        self.mount = self.runtime / "gvfs" / "mtp:host=SAMSUNG_SAMSUNG_Android_d0dcf43e7711e521"
        (self.mount / "Internal shared storage").mkdir(parents=True, exist_ok=True)
        (self.mount / "SD card").mkdir(exist_ok=True)
        self._env = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = str(self.runtime)
        self._orig = mtp._usb_dir
        usb = Path(helpers.ROOT) / f"usb-{self._testMethodName}" / "1-1"
        usb.mkdir(parents=True, exist_ok=True)
        (usb / "serial").write_text("d0dcf43e7711e521\n")
        mtp._usb_dir = lambda bus, num: usb

    def tearDown(self):
        mtp._usb_dir = self._orig
        if self._env is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self._env

    def test_the_mount_is_found_by_the_serial_and_its_storages_listed(self):
        d = mtp.Device("1:5", 1, 5, "Samsung", "Galaxy models")
        self.assertTrue(fuse.attach(d))
        self.assertEqual(([s.name for s in d.storages], d.backend, d.state), (["Internal shared storage", "SD card"], "fuse", "ready"))

    def test_no_mount_means_no_device(self):
        (self.mount / "SD card").rmdir()
        (self.mount / "Internal shared storage").rmdir()
        self.mount.rmdir()
        self.assertFalse(fuse.attach(mtp.Device("1:5", 1, 5, "Samsung", "Galaxy models")))

    def test_songs_are_copied_into_the_chosen_storage(self):
        d = mtp.Device("1:5", 1, 5, "Samsung", "Galaxy models")
        fuse.attach(d)
        song = Path(helpers.ROOT) / "fuse-song.mp3"
        song.write_bytes(b"audio" * 1000)
        item = transfer.Item("fuse-song.mp3", "Artist", "Album", path=str(song))
        result = transfer.send(d, [item], lambda *a: None, lambda: False, storage_id=1)
        self.assertEqual((result.sent, result.storage), (1, "SD card"))
        self.assertEqual((self.mount / "SD card" / "Music" / "Artist" / "fuse-song.mp3").read_bytes(), b"audio" * 1000)
        again = transfer.send(d, [item], lambda *a: None, lambda: False, storage_id=1)
        self.assertEqual((again.sent, again.skipped), (0, 1))

    def test_stopping_removes_the_half_copied_song(self):
        d = mtp.Device("1:5", 1, 5, "Samsung", "Galaxy models")
        fuse.attach(d)
        song = Path(helpers.ROOT) / "fuse-big.mp3"
        song.write_bytes(b"x" * (3 << 20))
        item = transfer.Item("fuse-big.mp3", "A", "B", path=str(song))
        calls = {"n": 0}

        def cancelled():                                   # not asked to stop at the start, but once the copy is under way
            calls["n"] += 1
            return calls["n"] > 1
        result = transfer.send(d, [item], lambda *a: None, cancelled, storage_id=0)
        self.assertTrue(result.cancelled)
        self.assertGreater(calls["n"], 1)
        self.assertFalse((self.mount / "Internal shared storage" / "Music" / "A" / "fuse-big.mp3").exists())


class DeviceWindowTests(unittest.TestCase):
    def setUp(self):
        translator.set_language("en")
        self._libmtp = mtp._libmtp
        mtp._libmtp = False                     # no real scanning: whatever is plugged into this computer must not join the test
        self.window, self.cfg, self.db, self.engine, self.eq = make_window(f"devices-{self._testMethodName}", n=8)
        self.sent = []
        self.window.devices.send = lambda key, items, storage=None: self.sent.append((key, items)) or True
        self.window.devices.set_active(False)
        self.window.devices._timer.stop()

    def tearDown(self):
        self.window.close()
        mtp._libmtp = self._libmtp

    def plug(self, *devices):
        self.window.devices.devices = list(devices)
        self.window.devices.changed.emit()
        pump(30)

    def test_the_device_shows_above_library_and_only_while_plugged_in(self):
        sidebar = self.window.sidebar
        header = sidebar._headers["devices"]
        self.assertTrue(header.isHidden())
        self.plug(make_device())
        self.assertFalse(header.isHidden())
        top = [sidebar.topLevelItem(i) for i in range(sidebar.topLevelItemCount())]
        self.assertIs(top[0], header)
        self.assertEqual(top[1], sidebar._headers["library"])
        self.assertEqual(header.child(0).text(0), "Galaxy Tab")
        self.assertEqual(header.text(0), "DEVICES")
        self.plug()
        self.assertTrue(header.isHidden())

    def test_the_page_says_what_to_do_when_the_phone_only_charges(self):
        self.plug(make_device(state="waiting", name=""))
        self.window.sidebar.select("device", "1:5")
        self.window._show_view("device", "1:5")
        view = self.window.device_view
        self.assertIs(self.window.stack.currentWidget(), view)
        self.assertIn("File transfer", view.hint.text())
        self.assertFalse(view.hint.isHidden())
        self.assertFalse(view.send_songs.isVisibleTo(view))
        self.assertTrue(view.check.isVisibleTo(view))

    def test_the_page_of_a_ready_device_shows_room_and_send_buttons(self):
        self.plug(make_device())
        self.window._show_view("device", "1:5")
        view = self.window.device_view
        self.assertTrue(view.send_songs.isVisibleTo(view))
        self.assertEqual(view.storage_box.count(), 1)
        self.assertEqual(self.window.title_label.text(), "Galaxy Tab")
        texts = [label.text() for label in view.findChildren(QLabel)]
        self.assertIn("20.0 GB free of 64.0 GB", texts)

    def test_it_follows_the_device_when_the_usb_mode_re_plugs_it(self):
        self.plug(make_device("1:2", state="waiting"))
        self.window._show_view("device", "1:2")
        self.plug(make_device("1:7"))                                        # same tablet, new USB number, now in MTP mode
        self.assertEqual(self.window._view, ("device", "1:7"))
        self.assertTrue(self.window.device_view.send_songs.isVisibleTo(self.window.device_view))

    def test_the_page_is_left_when_the_device_is_unplugged(self):
        self.plug(make_device())
        self.window._show_view("device", "1:5")
        self.plug()
        self.assertEqual(self.window._view, ("all", None))
        self.assertIs(self.window.stack.currentWidget(), self.window.table)

    def test_right_click_menu_offers_only_ready_devices(self):
        self.plug(make_device("1:5", name="Tab"), make_device("1:6", state="waiting", name="Other"))
        self.assertEqual(self.window.table.devices, [("1:5", "Tab")])

    def test_dropping_songs_on_the_device_hands_them_to_the_window(self):
        self.plug(make_device())
        sidebar = self.window.sidebar
        got = []
        sidebar.device_tracks_dropped.connect(lambda key, ids: got.append((key, ids)))
        _, over, dropped = drag_through(sidebar, sidebar._items[("device", "1:5")], tracks_mime([1, 2, 3]))
        self.assertTrue(over and dropped)
        self.assertEqual(got, [("1:5", [1, 2, 3])])

    def test_local_songs_are_sent_from_where_they_are(self):
        self.plug(make_device())
        song = Path(helpers.ROOT) / "real.mp3"
        song.write_bytes(b"x")
        track = self.db.tracks_by_ids([1])[0]
        self.db.connect().execute("UPDATE tracks SET location=? WHERE id=?", (str(song), track.id))
        self.db.connect().commit()
        self.window._send_tracks_to_device("1:5", [track.id])
        key, items = self.sent[0]
        self.assertEqual((key, items[0].name, items[0].path), ("1:5", "real.mp3", str(song)))
        self.assertEqual((items[0].artist, items[0].album), (track.artist, track.album))

    def test_dropping_files_from_the_file_manager_sends_the_audio_in_them(self):
        self.plug(make_device())
        folder = Path(helpers.ROOT) / "drop-files"
        folder.mkdir(exist_ok=True)
        (folder / "x.mp3").write_bytes(b"x")
        (folder / "notes.txt").write_bytes(b"x")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(folder))])
        sidebar = self.window.sidebar
        _, over, dropped = drag_through(sidebar, sidebar._items[("device", "1:5")], mime)
        self.assertTrue(over and dropped)
        key, items = self.sent[0]
        self.assertEqual((key, [i.name for i in items]), ("1:5", ["x.mp3"]))

    def test_a_device_cannot_take_a_folder_drag_or_a_waiting_one_a_send(self):
        self.plug(make_device(state="waiting"))
        self.window._start_send("1:5", [transfer.Item("a.mp3", path="/x/a.mp3")])
        self.assertEqual(self.sent, [])

    def make_folder(self, name="Bachata"):
        folder_id = self.window.folders.create(name)
        self.window.refresh_folders()
        pump(30)
        return folder_id

    def test_a_juke_folder_is_sent_from_its_right_click_menu(self):
        from PySide6.QtWidgets import QMenu

        folder_id = self.make_folder()
        self.window._folder_ids = lambda fid: [1, 2, 3] if fid == folder_id else []
        self.plug(make_device(name="Tab"))
        sidebar = self.window.sidebar
        menu = QMenu()
        sidebar._folder_menu(menu, sidebar._items[("ufolder", folder_id)], folder_id)
        action = next(a for a in menu.actions() if a.text() == "Send to Tab")
        self.window._send_tracks_to_device = lambda key, ids, folder="": self.sent.append((key, ids, folder))
        action.trigger()
        self.assertEqual(self.sent, [("1:5", [1, 2, 3], "Bachata")])                 # and the folder's name is the one on the phone

    def test_a_device_that_is_not_ready_is_not_offered_in_the_folder_menu(self):
        from PySide6.QtWidgets import QMenu

        folder_id = self.make_folder()
        self.plug(make_device(state="waiting"))
        sidebar = self.window.sidebar
        menu = QMenu()
        sidebar._folder_menu(menu, sidebar._items[("ufolder", folder_id)], folder_id)
        self.assertFalse([a for a in menu.actions() if a.text().startswith("Send to")])

    def test_dragging_a_juke_folder_onto_the_device_sends_it(self):
        folder_id = self.make_folder()
        self.plug(make_device())
        sidebar = self.window.sidebar
        got = []
        sidebar.device_folder_dropped.connect(lambda key, fid: got.append((key, fid)))
        mime = QMimeData()
        mime.setData(MIME_FOLDER, str(folder_id).encode())
        _, over, dropped = drag_through(sidebar, sidebar._items[("device", "1:5")], mime, Qt.MoveAction)
        self.assertTrue(over and dropped)
        self.assertEqual(got, [("1:5", folder_id)])

    def test_the_device_page_lists_the_juke_folders_and_sends_the_chosen_one(self):
        parent = self.make_folder("Music")
        child = self.window.folders.create("Salsa", parent)
        self.window.refresh_folders()
        self.plug(make_device())
        self.window._show_view("device", "1:5")
        view = self.window.device_view
        self.assertTrue(view.send_juke.isVisibleTo(view))
        view._fill_menu(view.folder_menu, None)
        top = [a.text() for a in view.folder_menu.actions()]
        self.assertEqual(len(top), 1)
        self.assertTrue(top[0].startswith("Music"))
        sub = view.folder_menu.actions()[0].menu()
        view._fill_menu(sub, parent)
        self.assertEqual([a.text() for a in sub.actions() if a.text()][:1], ["This Folder"])
        got = []
        view.folder_chosen.connect(lambda key, fid: got.append((key, fid)))
        sub.actions()[0].trigger()
        self.assertEqual(got, [("1:5", parent)])

    def test_a_juke_folder_goes_to_the_phone_as_one_folder_of_that_name(self):
        folder_id = self.make_folder("Sin Fronteras")
        self.window._folder_ids = lambda fid: [1, 2]
        sent = []
        self.window._start_send = lambda key, items: sent.append(items)
        self.window._send_folder_to_device("1:5", folder_id)
        self.assertEqual({item.folder for item in sent[0]}, {"Sin Fronteras"})

    def test_a_folder_from_disk_keeps_its_name_and_loose_files_go_by_artist(self):
        root = Path(helpers.ROOT) / "picked" / "Bachata Mix"
        root.mkdir(parents=True, exist_ok=True)
        (root / "one.mp3").write_bytes(b"x")
        loose = Path(helpers.ROOT) / "picked" / "loose.mp3"
        loose.write_bytes(b"x")
        sent = []
        self.window._start_send = lambda key, items: sent.append(items)
        self.window._send_paths_to_device("1:5", [str(root), str(loose)])
        self.assertEqual([(i.name, i.folder) for i in sent[0]], [("one.mp3", "Bachata Mix"), ("loose.mp3", "")])

    def test_sending_a_folder_with_nothing_in_it_says_so(self):
        self.plug(make_device())
        self.window._folder_ids = lambda fid: []
        self.window._send_folder_to_device("1:5", 1)
        self.assertEqual(self.sent, [])
        self.assertNotEqual(self.window.statusBar().currentMessage(), "")

    def storages(self, *names):
        return [mtp.Storage(i + 1, name, 64 << 30, 20 << 30, writable=not name.startswith("Locked")) for i, name in enumerate(names)]

    def test_a_device_with_a_card_lets_you_choose_where_songs_go(self):
        card = make_device()
        card.storages = self.storages("Internal storage", "SD card", "Locked")
        self.plug(card)
        self.window._show_view("device", "1:5")
        view = self.window.device_view
        self.assertTrue(view.target_row.isVisibleTo(view))
        self.assertEqual([view.target.itemText(i).split(" · ")[0] for i in range(view.target.count())], ["Internal storage", "SD card"])
        self.assertIsNone(view.storage_for(card))                        # nothing chosen yet: the first writable one
        view.target.setCurrentIndex(1)
        self.assertEqual(view.storage_for(card), 2)
        self.window._start_send("1:5", [transfer.Item("a.mp3", path="/x/a.mp3")])
        self.assertEqual(len(self.sent), 1)

    def test_a_device_with_only_internal_memory_shows_no_choice(self):
        self.plug(make_device())
        self.window._show_view("device", "1:5")
        view = self.window.device_view
        self.assertFalse(view.target_row.isVisibleTo(view))
        self.assertIsNone(view.storage_for(self.window.devices.get("1:5")))

    def test_the_choice_is_remembered_when_the_device_is_plugged_in_again(self):
        first = make_device("1:5")
        first.storages = self.storages("Internal storage", "SD card")
        self.plug(first)
        self.window._show_view("device", "1:5")
        self.window.device_view.target.setCurrentIndex(1)
        again = make_device("1:8")
        again.storages = self.storages("Internal storage", "SD card")
        self.plug(again)
        self.assertEqual(self.window.device_view.target.currentData(), 2)

    def test_the_message_says_which_storage_it_went_to_only_when_there_was_a_choice(self):
        card = make_device()
        card.storages = self.storages("Internal storage", "SD card")
        self.plug(card)
        self.window._device_sent("1:5", transfer.Result(sent=2, storage="SD card"))
        self.assertEqual(self.window.statusBar().currentMessage(), "Sent 2 songs to Galaxy Tab (SD card)")
        self.plug(make_device())
        self.window._device_sent("1:5", transfer.Result(sent=2, storage="Internal storage"))
        self.assertEqual(self.window.statusBar().currentMessage(), "Sent 2 songs to Galaxy Tab")

    def test_putting_a_card_in_counts_as_a_change(self):
        from juke.devices import manager as mgr

        seen = []
        self.window.devices.changed.connect(lambda: seen.append(1))
        one = make_device()
        one.storages = self.storages("Internal storage")
        self.window.devices._scanned([one])
        two = make_device()
        two.storages = self.storages("Internal storage", "SD card")
        self.window.devices._scanned([two])
        self.window.devices._scanned([two])
        self.assertEqual(len(seen), 2)                                   # the card was noticed, and the same list again was not

    def test_sending_reports_what_happened(self):
        self.plug(make_device())
        result = transfer.Result(sent=3, skipped=2, failed=["z"])
        self.window._device_sent("1:5", result)
        shown = self.window.statusBar().currentMessage()
        self.assertEqual(shown, "Sent 3 songs to Galaxy Tab · 2 were already there · 1 could not be sent")
        self.window._device_sent("1:5", transfer.Result(skipped=4))
        self.assertEqual(self.window.statusBar().currentMessage(), "Everything was already on Galaxy Tab")
        translator.set_language("es")
        self.window._device_sent("1:5", transfer.Result(sent=1))
        self.assertEqual(self.window.statusBar().currentMessage(), "1 canción enviada a Galaxy Tab")
        translator.set_language("en")


if __name__ == "__main__":
    unittest.main()


class LibraryTests(unittest.TestCase):
    """Reading what a device already holds, and taking songs off it."""

    class Tree:
        """A device as the sessions show it: folders of entries, by ref."""

        def __init__(self):
            self.folders = {
                "/": {"Music": ("d", "/Music"), "Download": ("d", "/Download"), "Android": ("d", "/Android"), "root.mp3": ("f", "/root.mp3")},
                "/Music": {"Alex Bueno": ("d", "/Music/Alex Bueno"), "loose.flac": ("f", "/Music/loose.flac"), "cover.jpg": ("f", "/Music/cover.jpg")},
                "/Music/Alex Bueno": {"Best Of": ("d", "/Music/Alex Bueno/Best Of"), "single.mp3": ("f", "/Music/Alex Bueno/single.mp3")},
                "/Music/Alex Bueno/Best Of": {"01 - Amor.mp3": ("f", "/Music/Alex Bueno/Best Of/01 - Amor.mp3"),
                                              "02 Vida.m4a": ("f", "/Music/Alex Bueno/Best Of/02 Vida.m4a")},
                "/Download": {"Sermon": ("d", "/Download/Sermon"), "talk.mp3": ("f", "/Download/talk.mp3")},
                "/Download/Sermon": {"deep": ("d", "/Download/Sermon/deep")},
                "/Download/Sermon/deep": {"too deep": ("d", "/Download/Sermon/deep/too deep")},
                "/Download/Sermon/deep/too deep": {"hidden.mp3": ("f", "/Download/Sermon/deep/too deep/hidden.mp3")},
                "/Android": {"data.mp3": ("f", "/Android/data.mp3")},
            }
            self.deleted = []

    def setUp(self):
        self.tree = self.Tree()
        tree = self.tree
        self._orig = mtp.open_session

        class Session:
            def __init__(self, device, wait=True):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return None

            def storages(self):
                return [mtp.Storage(1, "Internal", 100, 50), mtp.Storage(2, "SD card", 100, 50)]

            def root(self, storage):
                return "/"

            def children(self, storage, ref="/", refresh=False):
                if storage == 2:
                    return {}
                return {name: mtp.Entry(0, name, 1000, kind == "d", path) for name, (kind, path) in tree.folders.get(ref, {}).items()}

            def delete(self, storage, ref):
                if ref.endswith("Vida.m4a"):
                    raise mtp.MtpError("no")
                tree.deleted.append(ref)

        mtp.open_session = lambda device, wait=True: Session(device, wait)

    def tearDown(self):
        mtp.open_session = self._orig

    def test_titles_artists_and_albums_come_from_the_folders(self):
        from juke.devices import library

        self.assertEqual(library.describe("Music", ["Alex Bueno", "Best Of", "01 - Amor.mp3"]), ("Alex Bueno", "Best Of", "Amor"))
        self.assertEqual(library.describe("Music", ["Alex Bueno", "single.mp3"]), ("Alex Bueno", "", "single"))
        self.assertEqual(library.describe("Music", ["loose.flac"]), ("", "", "loose"))
        self.assertEqual(library.describe("Music", ["A", "B", "C", "07. Song.mp3"]), ("A", "B/C", "Song"))
        self.assertEqual(library.describe("Download", ["Sermon", "talk.mp3"]), ("Download", "Sermon", "talk"))
        self.assertEqual(library.describe("Music", ["2 Unlimited.mp3"])[2], "Unlimited")       # a number and a space is a track number
        self.assertEqual(library.describe("Music", ["1999.mp3"])[2], "1999")                    # ...but a title that is only a number is kept

    def test_the_usual_folders_are_read_and_the_rest_of_the_phone_is_left_alone(self):
        from juke.config import AUDIO_EXTENSIONS
        from juke.devices import library

        counted = []
        songs = library.scan(make_device(), AUDIO_EXTENSIONS, counted.append)
        names = sorted(s.filename for s in songs)
        self.assertEqual(names, ["01 - Amor.mp3", "02 Vida.m4a", "loose.flac", "single.mp3", "talk.mp3"])   # no cover.jpg, no Android/, nothing too deep
        amor = next(s for s in songs if s.title == "Amor")
        self.assertEqual((amor.artist, amor.album, amor.storage_name), ("Alex Bueno", "Best Of", "Internal"))
        self.assertTrue(counted and counted[-1] == len(songs))

    def test_stopping_a_read_returns_what_was_found(self):
        from juke.config import AUDIO_EXTENSIONS
        from juke.devices import library

        self.assertEqual(library.scan(make_device(), AUDIO_EXTENSIONS, cancelled=lambda: True), [])

    def test_removing_counts_what_worked_and_what_did_not(self):
        from juke.config import AUDIO_EXTENSIONS
        from juke.devices import library

        songs = library.scan(make_device(), AUDIO_EXTENSIONS)
        pick = [s for s in songs if s.filename in ("01 - Amor.mp3", "02 Vida.m4a")]
        self.assertEqual(library.remove(make_device(), pick), (1, 1))
        self.assertEqual(self.tree.deleted, ["/Music/Alex Bueno/Best Of/01 - Amor.mp3"])


class DeviceSongsViewTests(unittest.TestCase):
    def setUp(self):
        translator.set_language("en")
        from juke.devices.library import Song

        self.Song = Song
        self.window, *_ = make_window(f"songs-{self._testMethodName}", n=3)
        self.window.devices._timer.stop()
        self.window.devices.read_songs = lambda key: True                 # the reading itself is tested above
        self.window.devices.devices = [make_device()]
        self.window.devices.changed.emit()
        self.window._show_view("device", "1:5")
        pump(30)
        self.view = self.window.device_view
        self.songs = [Song("Alex Bueno", "Best Of", "Amor", "01 Amor.mp3", 5 << 20, 1, "Internal", "/a"),
                      Song("Alex Bueno", "Best Of", "Vida", "02 Vida.mp3", 4 << 20, 1, "Internal", "/b"),
                      Song("Alex Bueno", "", "Single", "s.mp3", 3 << 20, 1, "Internal", "/c"),
                      Song("Sandy Reyes", "Hits", "Baila", "b.mp3", 6 << 20, 1, "Internal", "/d")]

    def tearDown(self):
        self.window.close()

    def texts(self, item):
        return [(item.child(i).text(0), item.child(i).text(1)) for i in range(item.childCount())]

    def test_the_songs_on_the_device_are_listed_by_artist_and_album(self):
        self.view.set_songs(self.songs)
        tree = self.view.tree
        self.assertEqual([tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())], ["Alex Bueno", "Sandy Reyes"])
        alex = tree.topLevelItem(0)
        self.assertEqual(alex.text(1), "3 songs")
        self.assertEqual([c.text(0) for c in [alex.child(i) for i in range(alex.childCount())]], ["Best Of", "Single"])
        self.assertEqual(self.texts(alex.child(0)), [("Amor", "5.0 MB"), ("Vida", "4.0 MB")])
        self.assertEqual(self.view.songs_status.text(), "4 songs on the device")

    def test_an_empty_device_says_so(self):
        self.view.set_songs([])
        self.assertEqual(self.view.songs_status.text(), "No music on this device yet")
        self.assertFalse(self.view.drop_hint.isHidden())                  # the hint about how to fill it stays while it is empty

    def test_the_hint_gives_way_to_the_list(self):
        self.view.set_songs(self.songs)
        self.assertTrue(self.view.drop_hint.isHidden())

    def test_the_search_box_filters_the_device(self):
        self.view.set_songs(self.songs)
        self.window.search.setText("baila")
        pump(400)
        tree = self.view.tree
        self.assertEqual(tree.topLevelItemCount(), 1)
        self.assertEqual(self.view.songs_status.text(), "1 song found")
        self.window.search.setText("")
        pump(400)
        self.assertEqual(tree.topLevelItemCount(), 2)

    def test_removing_asks_first_and_only_then_removes(self):
        self.view.set_songs(self.songs)
        asked, removed = [], []
        self.window.devices.remove = lambda key, songs: removed.append((key, [s.title for s in songs])) or True
        orig = mw.confirm
        try:
            mw.confirm = lambda parent, title, text: asked.append(text) or False
            self.view.tree.topLevelItem(0).setSelected(True)
            self.view._remove_selected()
            self.assertEqual((asked, removed), (["Remove 3 songs from Galaxy Tab? The files are deleted from the device."], []))
            mw.confirm = lambda parent, title, text: True
            self.view._remove_selected()
        finally:
            mw.confirm = orig
        self.assertEqual(removed, [("1:5", ["Amor", "Vida", "Single"])])

    def test_selecting_an_album_and_one_of_its_songs_removes_each_song_once(self):
        self.view.set_songs(self.songs)
        alex = self.view.tree.topLevelItem(0)
        alex.setExpanded(True)
        alex.child(0).setSelected(True)
        alex.child(0).child(0).setSelected(True)
        self.assertEqual([s.title for s in self.view._selected_songs()], ["Amor", "Vida"])

    def test_the_list_is_read_again_after_songs_are_removed(self):
        reads = []
        self.window.devices.read_songs = lambda key: reads.append(key) or True
        self.window._device_removed("1:5", 2, 1)
        pump(50)
        self.assertEqual(reads, ["1:5"])
        self.assertIn("Removed 2 songs from Galaxy Tab · 1 could not be removed", self.window.statusBar().currentMessage())


class EjectTests(unittest.TestCase):
    def setUp(self):
        translator.set_language("en")
        self.window, *_ = make_window(f"eject-{self._testMethodName}", n=3)
        self.window.devices._timer.stop()
        self.window.devices.read_songs = lambda key: True
        self.manager = self.window.devices
        self.manager.devices = [make_device()]
        self.manager.changed.emit()
        pump(30)

    def tearDown(self):
        self.window.close()

    def test_ejecting_takes_the_device_off_the_list_and_says_it_can_be_unplugged(self):
        self.window._eject_device("1:5")
        pump(50)
        self.assertEqual(self.manager.devices, [])
        self.assertTrue(self.window.sidebar._headers["devices"].isHidden())
        self.assertEqual(self.window.statusBar().currentMessage(), "Galaxy Tab can be unplugged now")

    def test_an_ejected_device_stays_away_until_it_is_plugged_in_again(self):
        self.window._eject_device("1:5")
        pump(50)
        self.manager._scanned([make_device()])                          # the same device still plugged in: not brought back
        self.assertEqual(self.manager.devices, [])
        self.manager._scanned([])                                       # unplugged...
        self.manager._scanned([make_device()])                          # ...and plugged in again
        self.assertEqual([d.key for d in self.manager.devices], ["1:5"])

    def test_ejecting_from_the_device_page_goes_back_to_the_library(self):
        self.window._show_view("device", "1:5")
        self.window.device_view.eject.click()
        pump(80)
        self.assertEqual(self.window._view, ("all", None))

    def test_the_sidebar_row_has_an_eject_button_and_a_menu_entry(self):
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QMenu

        sidebar = self.window.sidebar
        got = []
        sidebar.device_eject_requested.connect(got.append)
        item = sidebar._items[("device", "1:5")]
        rect = sidebar._eject_rect(item)
        self.assertTrue(sidebar.visualItemRect(item).contains(rect))
        press = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(rect.center()), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(sidebar.viewport(), press)
        self.assertEqual(got, ["1:5"])
        row = sidebar.visualItemRect(item)
        elsewhere = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(QPoint(row.left() + 40, row.center().y())), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(sidebar.viewport(), elsewhere)
        self.assertEqual(got, ["1:5"])                                  # the rest of the row only selects the device

    def test_a_transfer_in_progress_asks_before_ejecting(self):
        asked = []
        self.manager._send = object()                                   # something is being copied
        ejected = []
        self.manager.eject = ejected.append
        orig = mw.confirm
        try:
            mw.confirm = lambda parent, title, text: asked.append(text) or False
            self.window._eject_device("1:5")
            self.assertEqual((len(asked), ejected), (1, []))
            mw.confirm = lambda parent, title, text: True
            self.window._eject_device("1:5")
        finally:
            mw.confirm = orig
            self.manager._send = None
        self.assertEqual(ejected, ["1:5"])

    def test_a_device_that_cannot_be_used_yet_can_be_ejected_too(self):
        self.manager.devices = [make_device(state="waiting")]
        self.manager.changed.emit()
        self.window._show_view("device", "1:5")
        view = self.window.device_view
        self.assertTrue(view.eject_alt.isVisibleTo(view))
        self.assertFalse(view.eject.isVisibleTo(view))
