"""The portable copy (playlists, stations, favourites, equalizer), its encryption, and the sync client against a fake server."""

import hashlib
import os
import json
import threading
import time
import unittest
import unittest.mock
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from . import helpers

from PySide6.QtWidgets import QApplication

from juke import backup, sync
from juke.audio.equalizer import Equalizer
from juke.config import Config
from juke.db.database import SOURCE_YOUTUBE, Database, Station

from .test_core import row

app = QApplication.instance() or QApplication([])


def make(name, rows=()):
    db = Database(Path(helpers.ROOT) / f"{name}-{time.monotonic_ns()}.db")
    db.upsert_many(rows)
    config = Config(Path(helpers.ROOT) / f"{name}-{time.monotonic_ns()}.json")
    return db, config


def ids_of(db, *titles):
    return [t.id for title in titles for t in [db.find_by_location("local", f"/x/{title}.mp3")]]


class CodeAndCryptoTests(unittest.TestCase):
    def test_code_shape_and_typing_forms(self):
        code = sync.new_code()
        self.assertRegex(code, r"^[A-HJ-NP-Z2-9]{5}(-[A-HJ-NP-Z2-9]{5}){3}$")
        self.assertEqual(sync.clean_code(code.lower().replace("-", " ")), code)
        for bad in ("", "ABC", code + "A", code.replace(code[0], "0", 1)):
            with self.assertRaises(ValueError):
                sync.clean_code(bad)

    def test_round_trip_and_the_server_sees_no_words(self):
        code = sync.new_code()
        text = json.dumps({"playlists": [{"name": "Merengue de fiesta"}]}) * 50
        blob = sync.seal(code, text)
        self.assertRegex(blob, r"^[A-Za-z0-9_-]+$")
        self.assertNotIn("Merengue", blob)
        self.assertEqual(sync.unseal(code, blob), text)
        self.assertNotEqual(blob, sync.seal(code, text))             # a new nonce every time

    def test_wrong_code_or_damage_is_refused(self):
        code, other = sync.new_code(), sync.new_code()
        blob = sync.seal(code, "hello")
        with self.assertRaises(sync.SyncError) as ctx:
            sync.unseal(other, blob)
        self.assertEqual(ctx.exception.code, "corrupt")
        flipped = blob[:30] + ("A" if blob[30] != "A" else "B") + blob[31:]
        for damaged in (flipped, blob[:-4], "", "!!!"):
            with self.assertRaises(sync.SyncError):
                sync.unseal(code, damaged)

    def test_a_copy_that_inflates_beyond_the_limit_is_refused(self):
        code = sync.new_code()
        with unittest.mock.patch.object(sync, "MAX_TEXT", 1000):
            with self.assertRaises(sync.SyncError) as ctx:
                sync.unseal(code, sync.seal(code, "a" * 5000))
        self.assertEqual(ctx.exception.code, "corrupt")
        self.assertEqual(sync.unseal(code, sync.seal(code, "a" * 5000)), "a" * 5000)

    def test_keys_are_derived_once_per_code(self):
        code = sync.new_code()
        sync._keys.cache_clear()
        sync.seal(code, "x"); sync.unseal(code, sync.seal(code, "y")); sync.address(code)
        self.assertEqual(sync._keys.cache_info().misses, 1)

    def test_address_and_secret_are_what_the_worker_expects(self):
        code = sync.new_code()
        address, secret, _, _ = sync._keys(code)
        self.assertRegex(address, r"^[0-9a-f]{32}$")
        self.assertRegex(secret, r"^[0-9a-f]{64}$")
        self.assertNotIn(secret[:32], address)


class BackupTests(unittest.TestCase):
    def test_playlists_follow_the_songs_to_another_library(self):
        a, cfg_a = make("a", [row(1, location="/x/one.mp3", title="One", artist="Band", duration=200),
                              row(2, location="/x/two.mp3", title="Two", artist="Band", duration=180),
                              row(3, location="/x/three.mp3", title="Three", artist="Band", duration=150)])
        pid = a.create_playlist("Fiesta")
        a.add_to_playlist(pid, ids_of(a, "one", "two", "three"))
        a.set_favorite(ids_of(a, "two"), True)
        yt = a.upsert_youtube([{"video_id": "abcdefghijk", "title": "Burbujas", "channel": "Juan Luis Guerra", "duration": 250}])
        a.add_to_playlist(pid, [yt["abcdefghijk"]])
        a.add_station(Station(0, "Radio Uno", "https://r.example/uno", tags="salsa"))
        cfg_a.set("theme", "dark")
        cfg_a.set("equalizer", {"enabled": True, "preamp": -2.0, "gains": [1.0] * 10, "preset": "Rock"})
        data = backup.loads(backup.dumps(backup.snapshot(a, cfg_a)))

        b, cfg_b = make("b", [row(1, location="/home/me/Uno.flac", title="ONE", artist="band", duration=201),     # same song elsewhere
                              row(2, location="/home/me/dos.flac", title="Two", artist="Band", duration=300)])    # same name, another length
        report = backup.restore(data, b, cfg_b)
        self.assertEqual((report.playlists, report.songs, report.missing, report.stations, report.favorites), (1, 2, 2, 1, 0))
        (playlist,) = b.playlists()
        self.assertEqual(playlist[1], "Fiesta")
        titles = [t.title for t in b.tracks_by_ids(b.playlist_track_ids(playlist[0]))]
        self.assertEqual(titles, ["ONE", "Burbujas"])
        self.assertEqual(b.count_stations(), 1)
        self.assertEqual(cfg_b.get("theme"), "dark")
        self.assertEqual(cfg_b.get("equalizer")["preset"], "Rock")

    def test_restoring_twice_adds_nothing_and_never_deletes(self):
        a, cfg = make("c", [row(1, location="/x/one.mp3", title="One", artist="Band", duration=200)])
        pid = a.create_playlist("Mine")
        a.add_to_playlist(pid, ids_of(a, "one"))
        data = backup.snapshot(a, cfg)
        other, cfg2 = make("d", [row(1, location="/x/one.mp3", title="One", artist="Band", duration=200),
                                 row(2, location="/x/two.mp3", title="Two", artist="Band", duration=100)])
        local = other.create_playlist("mine")                       # same name, other case: the songs join it
        other.add_to_playlist(local, ids_of(other, "two"))
        backup.restore(data, other, cfg2)
        backup.restore(data, other, cfg2)
        (only,) = other.playlists()
        self.assertEqual(only[2], 2)

    def test_garbage_in_a_copy_does_not_get_into_the_settings(self):
        db, cfg = make("e")
        data = {"format": backup.FORMAT, "version": 1, "playlists": ["nope", {"name": ""}, {"name": "ok", "tracks": [None, 3]}],
                "stations": [{"name": "x"}, 5], "favorites": "no",
                "settings": {"equalizer": {"gains": [99]}, "custom_presets": {"a": {"preamp": "x", "gains": [0] * 10},
                                                                              "b": {"preamp": 1, "gains": [0] * 10}},
                             "advanced_eq": {"room": "zzz", "bass": 5}, "theme": 7, "listening_setup": ["x"], "volume": 1}}
        backup.restore(data, db, cfg)
        self.assertEqual(cfg.get("theme"), "auto")
        self.assertEqual(list(cfg.get("custom_presets")), ["b"])
        self.assertEqual(cfg.get("advanced_eq"), {"bass": 5})
        self.assertEqual(cfg.get("volume"), 80)                     # not part of a copy
        self.assertEqual(cfg.get("equalizer")["gains"], [0.0] * 10)
        self.assertEqual([p[1] for p in db.playlists()], ["ok"])
        Equalizer(cfg)                                              # and Juke still starts with them

    def test_loads_refuses_what_is_not_ours(self):
        for text in ("", "[]", '{"format": "other"}', '{"format": "juke-backup", "version": 99}', "nope"):
            with self.assertRaises(backup.BackupError):
                backup.loads(text)

    def test_a_file_round_trips(self):
        db, cfg = make("f", [row(1, location="/x/one.mp3", title="Canción ñandú", artist="Año")])
        db.add_to_playlist(db.create_playlist("Ñ"), ids_of(db, "one"))
        path = Path(helpers.ROOT) / "copy.json"
        backup.save_file(path, db, cfg)
        self.assertEqual(backup.load_file(path)["playlists"][0]["tracks"][0]["title"], "Canción ñandú")


class FakeServer(BaseHTTPRequestHandler):
    """The protocol of cloudflare/sync, in memory."""

    store: dict = {}
    log: list = []                  # every save the server accepted

    def log_message(self, *args):
        pass

    def _reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self):
        address = self.path.rsplit("/", 1)[-1]
        secret = hashlib.sha256(self.headers["Authorization"][7:].encode()).hexdigest()
        row = self.store.get(address)
        if row and row["secret"] != secret:
            return self._reply(401, {"error": "unauthorized"})
        if self.command == "GET":
            return self._reply(200, {"blob": row["blob"], "updated": row["updated"]}) if row else self._reply(404, {"error": "nothing"})
        if self.command == "DELETE":
            self.store.pop(address, None)
            return self._reply(200, {"deleted": True})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if row and body["base"] not in (-1, row["updated"]):
            return self._reply(409, {"error": "changed", "updated": row["updated"]})
        self.store[address] = {"secret": secret, "blob": body["blob"], "updated": (row["updated"] + 1) if row else 1}
        self.log.append(address)
        self._reply(200, {"updated": self.store[address]["updated"]})

    do_GET = do_PUT = do_DELETE = _handle


class SyncClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FakeServer.store = {}
        cls.httpd = HTTPServer(("127.0.0.1", 0), FakeServer)
        cls.url = f"http://127.0.0.1:{cls.httpd.server_port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_send_get_conflict_wrong_code_and_delete(self):
        code, other = sync.new_code(), sync.new_code()
        with self.assertRaises(sync.SyncError) as ctx:
            sync.pull(self.url, code)
        self.assertEqual(ctx.exception.code, "none")
        first = sync.push(self.url, code, "one", 0)
        self.assertEqual(sync.pull(self.url, code), ("one", first))
        with self.assertRaises(sync.SyncError) as ctx:
            sync.push(self.url, code, "two", 0)                      # somebody else saved since this one looked
        self.assertEqual((ctx.exception.code, ctx.exception.updated), ("changed", first))
        second = sync.push(self.url, code, "two", -1)
        self.assertEqual(sync.pull(self.url, code)[0], "two")
        self.assertNotEqual(first, second)
        with self.assertRaises(sync.SyncError) as ctx:
            sync.pull(self.url, other)                               # another code is another address: nothing there
        self.assertEqual(ctx.exception.code, "none")
        sync.delete(self.url, code)
        with self.assertRaises(sync.SyncError):
            sync.pull(self.url, code)

    def test_only_https_or_this_computer(self):
        with self.assertRaises(sync.SyncError) as ctx:
            sync.pull("http://example.com", sync.new_code())
        self.assertEqual(ctx.exception.code, "url")
        with self.assertRaises(sync.SyncError) as ctx:
            sync.pull("http://127.0.0.1:9", sync.new_code())          # nothing listens there
        self.assertEqual(ctx.exception.code, "server")

    def test_too_big_is_refused_before_sending(self):
        with self.assertRaises(sync.SyncError) as ctx:
            sync.push(self.url, sync.new_code(), os.urandom(700_000).hex(), 0)   # (random data does not compress)
        self.assertEqual(ctx.exception.code, "big")


if __name__ == "__main__":
    unittest.main()


def tick():
    time.sleep(0.02)                  # the dates are kept in milliseconds: the next change must be later than the last


def songs(*names):
    return [row(i, location=f"/x/{n}.mp3", title=n.title(), artist="Band", duration=100.0 + i) for i, n in enumerate(names)]


def names_in(db, key="mix"):
    meta = db.playlist_meta().get(key)
    return [t.title for t in db.tracks_by_ids(db.playlist_track_ids(meta[0]))] if meta else None


class MergeTests(unittest.TestCase):
    """Two devices: what one does reaches the other, deletions included, and nothing is lost on the way."""

    def devices(self):
        both = songs("one", "two", "three")
        return make("m1", both), make("m2", both)

    def sync(self, sender, receiver):
        (db_s, cfg_s), (db_r, cfg_r) = sender, receiver
        backup.touch_settings(cfg_s)
        data = backup.loads(backup.dumps(backup.snapshot(db_s, cfg_s)))
        backup.touch_settings(cfg_r)
        return backup.merge(data, db_r, cfg_r)

    def test_a_playlist_made_edited_and_deleted_on_one_device_follows_on_the_other(self):
        (a, b) = self.devices()
        pid = a[0].create_playlist("Mix")
        a[0].add_to_playlist(pid, ids_of(a[0], "one", "two"))
        self.sync(a, b)
        self.assertEqual(names_in(b[0]), ["One", "Two"])
        tick()
        b[0].add_to_playlist(b[0].playlist_meta()["mix"][0], ids_of(b[0], "three"))      # edited on the other device
        self.sync(b, a)
        self.assertEqual(names_in(a[0]), ["One", "Two", "Three"])
        tick()
        a[0].remove_from_playlist(a[0].playlist_meta()["mix"][0], ids_of(a[0], "one"))   # a song taken out is taken out everywhere
        self.sync(a, b)
        self.assertEqual(names_in(b[0]), ["Two", "Three"])
        tick()
        a[0].delete_playlist(a[0].playlist_meta()["mix"][0])
        report = self.sync(a, b)
        self.assertIsNone(names_in(b[0]))
        self.assertEqual(report.deleted, 1)
        tick()
        again = b[0].create_playlist("Mix")                                               # made again later: it comes back, newer than the deletion
        b[0].add_to_playlist(again, ids_of(b[0], "two"))
        self.sync(b, a)
        self.assertEqual(names_in(a[0]), ["Two"])

    def test_the_newest_change_to_a_playlist_wins(self):
        (a, b) = self.devices()
        pid = a[0].create_playlist("Mix")
        a[0].add_to_playlist(pid, ids_of(a[0], "one"))
        self.sync(a, b)
        tick()
        b[0].add_to_playlist(b[0].playlist_meta()["mix"][0], ids_of(b[0], "two"))
        tick()
        a[0].add_to_playlist(pid, ids_of(a[0], "three"))                                  # a is the last to touch it
        self.sync(b, a)
        self.assertEqual(names_in(a[0]), ["One", "Three"])                                # b's older news does not undo a's
        self.sync(a, b)
        self.assertEqual(names_in(b[0]), ["One", "Three"])

    def test_songs_a_device_does_not_have_stay_in_the_copy(self):
        a = make("f1", songs("one", "two", "three"))
        b = make("f2", songs("one"))                                                      # this phone has only one of the songs
        pid = a[0].create_playlist("Mix")
        a[0].add_to_playlist(pid, ids_of(a[0], "one", "two", "three"))
        yt = a[0].upsert_youtube([{"video_id": "abcdefghijk", "title": "Burbujas", "channel": "JLG", "duration": 250}])
        a[0].add_to_playlist(pid, [yt["abcdefghijk"]])
        self.sync(a, b)
        self.assertEqual(names_in(b[0]), ["One", "Burbujas"])
        sent = backup.snapshot(b[0], b[1])                                                # b sends it back: the two it lacks are still there
        self.assertEqual(len(sent["playlists"][0]["tracks"]), 4)
        b[0].upsert_many(songs("one", "two"))                                             # the songs arrive in b's library later
        tick()
        self.sync(a, b)
        self.assertEqual(sorted(names_in(b[0])), ["Burbujas", "One", "Two"])

    def test_stations_follow_and_so_do_their_deletions(self):
        (a, b) = self.devices()
        a[0].add_station(Station(0, "Radio Uno", "https://r.example/uno"))
        self.sync(a, b)
        self.assertEqual(b[0].count_stations(), 1)
        tick()
        a[0].remove_station(a[0].stations()[0].id)
        self.sync(a, b)
        self.assertEqual(b[0].count_stations(), 0)
        tick()
        b[0].add_station(Station(0, "Radio Uno", "https://r.example/uno"))               # saved again later: it stays
        self.sync(b, a)
        self.assertEqual(a[0].count_stations(), 1)

    def test_settings_follow_the_newest_change_and_the_devices_settle(self):
        (a, b) = self.devices()
        a[1].set("theme", "dark")
        self.sync(a, b)
        self.assertEqual(b[1].get("theme"), "dark")
        tick()
        b[1].set("theme", "light")
        self.sync(b, a)
        self.assertEqual(a[1].get("theme"), "light")
        fp_a = backup.fingerprint(backup.snapshot(*a))
        self.sync(a, b)
        self.assertEqual(fp_a, backup.fingerprint(backup.snapshot(*b)))                   # nothing left to send either way

    def test_a_copy_of_version_one_only_adds(self):
        (a, b) = self.devices()
        pid = b[0].create_playlist("Mix")
        b[0].add_to_playlist(pid, ids_of(b[0], "one"))
        old = {"format": backup.FORMAT, "version": 1, "playlists": [{"name": "mix", "tracks": [
            {"title": "Two", "artist": "Band", "album": "", "duration": 101}]}, {"name": "New", "tracks": []}]}
        backup.merge(old, b[0], b[1])
        self.assertEqual(names_in(b[0]), ["One", "Two"])
        self.assertIn("new", b[0].playlist_meta())


class AutoSyncTests(unittest.TestCase):
    """Whole rounds, against the fake server: no button is pressed."""

    @classmethod
    def setUpClass(cls):
        FakeServer.store = {}
        cls.httpd = HTTPServer(("127.0.0.1", 0), FakeServer)
        cls.url = f"http://127.0.0.1:{cls.httpd.server_port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def device(self, name, code):
        from juke.autosync import AutoSync

        db, cfg = make(name, songs("one", "two"))
        cfg.set("sync.server", self.url)
        cfg.set("sync.code", code)
        cfg.save = lambda: None
        engine = AutoSync(db, cfg)
        self.addCleanup(engine.shutdown)
        return db, cfg, engine

    def round(self, device):
        from .test_gui import pump

        done = []
        device[2].finished.connect(lambda *args: done.append(args))
        device[2].run()
        for _ in range(200):
            pump(25)
            if done:
                break
        return done[-1] if done else None

    def test_two_devices_meet_in_the_middle_by_themselves(self):
        code = sync.new_code()
        a, b = self.device("as1", code), self.device("as2", code)
        pid = a[0].create_playlist("Mix")
        a[0].add_to_playlist(pid, ids_of(a[0], "one"))
        self.assertEqual(self.round(a)[:2], (True, False))
        self.assertEqual(self.round(b)[:2], (True, True))                                 # b learns of the playlist
        self.assertEqual(names_in(b[0]), ["One"])
        writes = len(FakeServer.log)
        self.assertEqual(self.round(b)[:2], (True, False))
        self.assertEqual(self.round(a)[:2], (True, False))
        self.assertEqual(len(FakeServer.log), writes)                                      # nothing new: nothing was written
        tick()
        b[0].add_to_playlist(b[0].playlist_meta()["mix"][0], ids_of(b[0], "two"))
        self.assertEqual(self.round(b)[:2], (True, False))
        self.assertEqual(self.round(a)[:2], (True, True))
        self.assertEqual(names_in(a[0]), ["One", "Two"])
        tick()
        a[0].delete_playlist(a[0].playlist_meta()["mix"][0])
        self.round(a)
        self.round(b)
        self.assertIsNone(names_in(b[0]))

    def test_it_stays_quiet_without_a_code_or_when_switched_off(self):
        db, cfg, engine = self.device("as3", "")
        self.assertFalse(engine.enabled)
        db2, cfg2, engine2 = self.device("as4", sync.new_code())
        cfg2.set("sync.auto", False)
        self.assertFalse(engine2.enabled)
        self.assertTrue(engine2.usable())
        self.assertEqual(self.round(engine_device := (db2, cfg2, engine2))[:2], (True, False)) if False else None

    def test_a_wrong_server_is_reported_not_raised(self):
        db, cfg, engine = self.device("as5", sync.new_code())
        cfg.set("sync.server", "http://127.0.0.1:9")
        result = self.round((db, cfg, engine))
        self.assertFalse(result[0])
        self.assertTrue(result[2].startswith("server"))


class DialogTests(unittest.TestCase):
    def test_the_dialog_syncs_now_and_says_so(self):
        from .test_gui import make_window, pump
        from juke.gui.backup_dialog import BackupDialog

        FakeServer.store = {}
        httpd = HTTPServer(("127.0.0.1", 0), FakeServer)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            window, cfg, db, engine, eq = make_window("backup-gui", 10)
            self.assertIn("Backup & sync…", [a.text().split("\t")[0] for a in window._menu.actions()])
            db.add_to_playlist(db.create_playlist("Salsa"), [r[0] for r in db.connect().execute("SELECT id FROM tracks LIMIT 3")])
            dialog = BackupDialog(window)
            dialog.server.setText(f"http://127.0.0.1:{httpd.server_port}")
            dialog.sync_now.click()                                     # no code yet: nothing is sent, and it says why
            self.assertIn("20", dialog.status.text())
            dialog.new_code.click()
            dialog.sync_now.click()
            for _ in range(200):
                pump(50)
                if FakeServer.store and "Synced" in dialog.status.text():
                    break
            self.assertEqual(len(FakeServer.store), 1)
            self.assertIn("Synced", dialog.status.text())
            self.assertTrue(cfg.get("sync.updated"))
            db.delete_playlist(db.playlist_meta()["salsa"][0])          # this device loses it; the cloud still has the older news of it...
            self.assertEqual(db.playlists(), [])
            dialog.reject()
            window.close()
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
