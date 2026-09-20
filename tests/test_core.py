import asyncio
import hashlib
import json
import math
import re
import struct
import unittest
import wave
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import helpers  # noqa: F401  (sets XDG env first)

import httpx

from juke.api.airsonic import AirsonicClient, AirsonicError, normalize_base_url, song_to_row
from juke.audio.queue import PlayQueue
from juke.config import Config, DEFAULTS
from juke.db.database import SOURCE_AIRSONIC, SOURCE_LOCAL, Database, Scope, normalize
from juke.db.indexer import iter_audio_files, read_tags, write_tags
from juke.locales import en, es


def make_db(name="lib.db") -> Database:
    return Database(Path(helpers.ROOT) / name)


def row(i, **kw):
    base = {"source_type": SOURCE_LOCAL, "location": f"/music/{i}.mp3", "title": f"Song {i}",
            "artist": f"Artist {i % 5}", "album": f"Album {i % 10}", "genre": "Rock" if i % 2 else "Jazz",
            "duration": 100.0 + i, "bitrate": 320, "track_no": i % 12}
    base.update(kw)
    return base


class DatabaseTests(unittest.TestCase):
    def test_indexes_exist_for_required_columns(self):
        db = make_db("idx.db")
        names = {r[0] for r in db.connect().execute("SELECT name FROM sqlite_master WHERE type='index'")}
        for wanted in ("idx_tracks_artist", "idx_tracks_album", "idx_tracks_title", "idx_tracks_genre", "idx_tracks_source_type"):
            self.assertIn(wanted, names)

    def test_upsert_keeps_favorites_and_updates_tags(self):
        db = make_db("up.db")
        db.upsert_many([row(1)])
        tid = db.query_ids()[0]
        db.set_favorite([tid], True)
        db.upsert_many([row(1, title="Renamed")])
        track = db.get_track(tid)
        self.assertTrue(track.favorite)
        self.assertEqual(track.title, "Renamed")
        self.assertEqual(db.count(), 1)

    def test_query_scope_search_sort(self):
        db = make_db("q.db")
        db.upsert_many([row(i) for i in range(50)])
        db.upsert_many([row(100, source_type=SOURCE_AIRSONIC, location="55", title="Canción Ñandú", artist="Sílvia")])
        self.assertEqual(len(db.query_ids()), 51)
        self.assertEqual(len(db.query_ids(Scope(source_type=SOURCE_AIRSONIC))), 1)
        self.assertEqual(len(db.query_ids(Scope(artist="artist 1"))), 10)  # case-insensitive
        self.assertEqual(len(db.query_ids(text="cancion nandu")), 1)       # accent-insensitive
        self.assertEqual(len(db.query_ids(text="silvia")), 1)
        by_dur = db.query_ids(sort="duration", descending=True)
        self.assertGreaterEqual(db.get_track(by_dur[0]).duration, db.get_track(by_dur[1]).duration)
        count, seconds = db.summary(Scope(artist="Artist 0"))
        self.assertEqual(count, 10)
        self.assertGreater(seconds, 1000)

    def test_tracks_by_ids_preserves_order_and_drops_missing(self):
        db = make_db("ids.db")
        db.upsert_many([row(i) for i in range(5)])
        ids = db.query_ids()
        wanted = [ids[3], 999999, ids[0]]
        self.assertEqual([t.id for t in db.tracks_by_ids(wanted)], [ids[3], ids[0]])

    def test_replace_source_removes_stale(self):
        db = make_db("rs.db")
        db.replace_source(SOURCE_AIRSONIC, [row(1, source_type=SOURCE_AIRSONIC, location="a"),
                                             row(2, source_type=SOURCE_AIRSONIC, location="b")])
        db.replace_source(SOURCE_AIRSONIC, [row(2, source_type=SOURCE_AIRSONIC, location="b")])
        self.assertEqual(db.locations(SOURCE_AIRSONIC), ["b"])

    def test_distinct_groups_case_insensitively_unknown_last(self):
        db = make_db("d.db")
        db.upsert_many([row(1, artist="abba"), row(2, artist="ABBA"), row(3, artist=""), row(4, artist="Zed")])
        names = [n for n, _ in db.distinct("artist")]
        self.assertEqual(len(names), 3)
        self.assertEqual(names[-1], "")

    def test_large_library_queries_stay_fast(self):
        import time
        db = make_db("big.db")
        db.upsert_many([row(i, location=f"/m/{i}") for i in range(60000)])
        start = time.perf_counter()
        ids = db.query_ids()
        natural = time.perf_counter() - start
        start = time.perf_counter()
        db.query_ids(text="song 59")
        search = time.perf_counter() - start
        start = time.perf_counter()
        db.tracks_by_ids(ids[30000:30256])
        page = time.perf_counter() - start
        self.assertEqual(len(ids), 60000)
        print(f"\n  60k tracks: natural order {natural*1000:.0f} ms, search {search*1000:.0f} ms, page fetch {page*1000:.1f} ms")
        self.assertLess(natural, 1.5)
        self.assertLess(search, 1.5)
        self.assertLess(page, 0.05)

    def test_folder_scope_is_recursive_and_escapes_wildcards(self):
        db = make_db("folders.db")
        A = dict(source_type=SOURCE_AIRSONIC)
        db.upsert_many([
            row(1, location="1", folder="Rock/Band One/Album A", **A),
            row(2, location="2", folder="Rock/Band One/Album B", **A),
            row(3, location="3", folder="Rock/Band Two/Album C", **A),
            row(4, location="4", folder="Rock 100%/x_y", **A),
            row(5, location="5", folder="Rockabilly/Other", **A),
        ])
        count = lambda folder: len(db.query_ids(Scope(source_type=SOURCE_AIRSONIC, folder=folder)))
        self.assertEqual(count("Rock"), 3)                       # Rock/... but not Rockabilly or "Rock 100%"
        self.assertEqual(count("Rock/Band One"), 2)
        self.assertEqual(count("Rock/Band One/Album A"), 1)
        self.assertEqual(count("Rock 100%"), 1)                  # % is literal, not a wildcard
        self.assertEqual(count("Rock 100%/x_y"), 1)
        self.assertEqual(count("Rock/Band _ne"), 0)              # _ is literal too
        self.assertEqual(sorted(db.folders(SOURCE_AIRSONIC))[0], "Rock 100%/x_y")

    def test_old_database_is_migrated(self):
        import sqlite3
        path = Path(helpers.ROOT) / "old.db"
        conn = sqlite3.connect(path)
        conn.executescript("CREATE TABLE tracks (id INTEGER PRIMARY KEY AUTOINCREMENT, source_type TEXT NOT NULL, location TEXT NOT NULL, "
                           "title TEXT NOT NULL DEFAULT '', artist TEXT NOT NULL DEFAULT '', album TEXT NOT NULL DEFAULT '', genre TEXT NOT NULL DEFAULT '', "
                           "year INTEGER NOT NULL DEFAULT 0, track_no INTEGER NOT NULL DEFAULT 0, duration REAL NOT NULL DEFAULT 0, bitrate INTEGER NOT NULL DEFAULT 0, "
                           "cover_key TEXT NOT NULL DEFAULT '', search_text TEXT NOT NULL DEFAULT '', mtime REAL NOT NULL DEFAULT 0, size INTEGER NOT NULL DEFAULT 0, "
                           "favorite INTEGER NOT NULL DEFAULT 0, play_count INTEGER NOT NULL DEFAULT 0, last_played REAL NOT NULL DEFAULT 0, added_at REAL NOT NULL DEFAULT 0, "
                           "UNIQUE (source_type, location)); INSERT INTO tracks (source_type, location, title) VALUES ('local', '/a.mp3', 'Kept');")
        conn.commit()
        conn.close()
        db = Database(path)
        self.assertEqual(db.count(), 1)
        db.upsert_many([row(2, folder="X/Y")])
        self.assertEqual(db.folders(SOURCE_LOCAL), ["X/Y"])

    def test_playlists_crud_order_and_cascade(self):
        db = make_db("pl.db")
        db.upsert_many([row(i) for i in range(6)])
        ids = db.query_ids()
        pid = db.create_playlist("  Fiesta ")
        db.add_to_playlist(pid, [ids[3], ids[1]])
        db.add_to_playlist(pid, [ids[5]])
        self.assertEqual(db.playlist_track_ids(pid), [ids[3], ids[1], ids[5]])   # insertion order, not library order
        self.assertEqual(db.playlists(), [(pid, "Fiesta", 3)])
        db.remove_from_playlist(pid, [ids[1]])
        self.assertEqual(db.playlist_track_ids(pid), [ids[3], ids[5]])
        db.rename_playlist(pid, "Domingo")
        self.assertEqual(db.playlists()[0][1], "Domingo")
        gone = db.get_track(ids[3])                   # a song leaving the library leaves its playlists
        db.delete_locations(SOURCE_LOCAL, [gone.location])
        self.assertEqual(db.playlist_track_ids(pid), [ids[5]])
        empty = db.create_playlist("Empty")
        self.assertIn((empty, "Empty", 0), db.playlists())
        db.delete_playlist(pid)
        self.assertEqual([p[1] for p in db.playlists()], ["Empty"])
        left = db.connect().execute("SELECT COUNT(*) FROM playlist_tracks").fetchone()[0]
        self.assertEqual(left, 0)

    def test_playlists_survive_an_airsonic_resync(self):
        db = make_db("plsync.db")
        db.replace_source(SOURCE_AIRSONIC, [row(1, source_type=SOURCE_AIRSONIC, location="a"), row(2, source_type=SOURCE_AIRSONIC, location="b")])
        ids = db.query_ids()
        pid = db.create_playlist("Server picks")
        db.add_to_playlist(pid, ids)
        db.replace_source(SOURCE_AIRSONIC, [row(1, source_type=SOURCE_AIRSONIC, location="a", title="Renamed on server")])
        self.assertEqual(len(db.playlist_track_ids(pid)), 1)   # kept the survivor, dropped the vanished song

    def test_normalize(self):
        self.assertEqual(normalize("Canción ÑANDÚ"), "cancion nandu")


class PlayQueueTests(unittest.TestCase):
    def test_context_and_next_prev(self):
        q = PlayQueue()
        q.set_context([1, 2, 3], 2)
        self.assertEqual(q.next(), 3)
        self.assertIsNone(q.next(auto=True))
        self.assertEqual(q.previous(), 2)

    def test_play_next_inserts_immediately_newest_first_and_add_appends(self):
        q = PlayQueue()
        q.set_context([1, 2, 3, 4], 1)
        q.add_to_queue([10])
        q.play_next([20])
        q.play_next([30])
        self.assertEqual(q.upcoming(), [30, 20, 10, 2, 3, 4])
        self.assertEqual(q.next(), 30)
        self.assertEqual(q.next(), 20)
        self.assertEqual(q.next(), 10)
        self.assertEqual(q.next(), 2)   # context resumes where it left off

    def test_repeat_modes(self):
        q = PlayQueue()
        q.set_context([1, 2], 2)
        q.repeat = "all"
        self.assertEqual(q.next(auto=True), 1)
        q.repeat = "one"
        self.assertEqual(q.next(auto=True), 1)
        self.assertEqual(q.next(auto=False), 2)

    def test_shuffle_keeps_current_first_and_is_permutation(self):
        q = PlayQueue()
        q.shuffle = True
        q.set_context(list(range(1, 30)), 7)
        self.assertEqual(q.order[0], 7)
        self.assertEqual(sorted(q.order), list(range(1, 30)))
        q.set_shuffle(False)
        self.assertEqual(q.order, list(range(1, 30)))
        self.assertEqual(q.order[q.cursor], 7)

    def test_view_and_remove(self):
        q = PlayQueue()
        q.set_context([1, 2, 3], 1)
        q.add_to_queue([9, 9, 8])
        q.remove_from_queue([9])
        self.assertEqual(q.view(), [1, 9, 8, 2, 3])
        q.clear_user_queue()
        self.assertEqual(q.view(), [1, 2, 3])


class ConfigTests(unittest.TestCase):
    def test_defaults_roundtrip_and_permissions(self):
        path = Path(helpers.ROOT) / "cfg" / "settings.json"
        cfg = Config(path)
        self.assertEqual(cfg.get("equalizer.preset"), "Flat")
        cfg.set("airsonic.url", "http://x")
        cfg.set("volume", 33)
        cfg.save()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        again = Config(path)
        self.assertEqual(again.get("airsonic.url"), "http://x")
        self.assertEqual(again.get("volume"), 33)
        self.assertEqual(again.get("language"), DEFAULTS["language"])

    def test_corrupt_file_falls_back_to_defaults(self):
        path = Path(helpers.ROOT) / "cfg2" / "settings.json"
        path.parent.mkdir(parents=True)
        path.write_text("{not json")
        self.assertEqual(Config(path).get("volume"), DEFAULTS["volume"])


class AirsonicTests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def make_client(self, handler):
        return AirsonicClient("music.local:4040/", "alice", "s3cret", transport=httpx.MockTransport(handler))

    def test_url_normalisation(self):
        self.assertEqual(normalize_base_url("music.local:4040/"), "http://music.local:4040")
        self.assertEqual(normalize_base_url("https://h/airsonic/rest"), "https://h/airsonic")

    def test_token_auth_is_md5_of_password_plus_salt(self):
        seen = {}

        def handler(request):
            seen.update({k: v[0] for k, v in parse_qs(request.url.query.decode()).items()})
            return httpx.Response(200, json={"subsonic-response": {"status": "ok", "version": "1.16.1"}})

        async def go():
            client = self.make_client(handler)
            try:
                return await client.ping()
            finally:
                await client.aclose()

        self.assertEqual(self.run_async(go()), "1.16.1")
        self.assertEqual(seen["u"], "alice")
        self.assertEqual(seen["t"], hashlib.md5(("s3cret" + seen["s"]).encode()).hexdigest())
        self.assertNotIn("p", seen)
        self.assertNotIn("s3cret", json.dumps(seen))

    def test_error_response_raises(self):
        handler = lambda r: httpx.Response(200, json={"subsonic-response": {"status": "failed", "error": {"code": 40, "message": "Wrong username or password"}}})

        async def go():
            client = self.make_client(handler)
            try:
                await client.ping()
            finally:
                await client.aclose()

        with self.assertRaises(AirsonicError) as ctx:
            self.run_async(go())
        self.assertEqual(ctx.exception.code, 40)

    def _server(self, tree, indexes, folders=None):
        """A tiny fake Subsonic server: getMusicFolders / getIndexes / getMusicDirectory."""
        def handler(request):
            params = parse_qs(request.url.query.decode())
            path = request.url.path
            if path.endswith("getMusicFolders.view"):
                body = {"musicFolders": {"musicFolder": folders or []}}
            elif path.endswith("getIndexes.view"):
                body = {"indexes": indexes(params.get("musicFolderId", [None])[0])}
            else:
                body = {"directory": tree[params["id"][0]]}
            return httpx.Response(200, json={"subsonic-response": {"status": "ok", **body}})
        return handler

    def sync(self, handler):
        async def go():
            client = self.make_client(handler)
            try:
                return await client.sync_library()
            finally:
                await client.aclose()
        return {r["location"]: r for r in self.run_async(go())}

    def test_sync_builds_folder_trail_from_the_directories_walked(self):
        tree = {
            "ba": {"child": [{"id": "ba1", "isDir": True, "title": "Romeo Santos"}, {"id": "s3", "title": "Loose"}]},
            "ba1": {"child": [{"id": "ba2", "isDir": True, "title": "Formula Vol. 1"}]},
            "ba2": {"child": [{"id": "s1", "title": "One", "artist": "Romeo", "album": "Al", "duration": 61, "bitRate": 256,
                               "coverArt": "ba2", "track": 1, "year": 1999, "genre": "Bachata"},
                              {"id": "s2", "title": "Two", "path": "ignored/because/trail/wins.mp3"}]},
            "me": {"child": {"id": "s4", "title": "Single dict child"}},
        }
        indexes = lambda folder: {"index": [{"name": "B", "artist": [{"id": "ba", "name": "Bachata"}, {"id": "me", "name": "Merengue"}]}],
                                  "child": [{"id": "s0", "title": "Root song"}]}
        rows = self.sync(self._server(tree, indexes))
        self.assertEqual(sorted(rows), ["s0", "s1", "s2", "s3", "s4"])
        self.assertEqual(rows["s1"]["folder"], "Bachata/Romeo Santos/Formula Vol. 1")
        self.assertEqual(rows["s2"]["folder"], "Bachata/Romeo Santos/Formula Vol. 1")
        self.assertEqual(rows["s3"]["folder"], "Bachata")
        self.assertEqual(rows["s4"]["folder"], "Merengue")
        self.assertEqual(rows["s0"]["folder"], "")
        one = rows["s1"]
        self.assertEqual((one["title"], one["duration"], one["bitrate"], one["cover_key"], one["source_type"]),
                         ("One", 61.0, 256, "as_ba2", "airsonic"))

    def test_separate_music_folders_become_the_first_level(self):
        tree = {"a1": {"child": [{"id": "x1", "title": "Song A"}]}, "b1": {"child": [{"id": "x2", "title": "Song B"}]}}
        by_folder = {"1": {"index": [{"artist": [{"id": "a1", "name": "Aventura"}]}]},
                     "2": {"index": [{"artist": [{"id": "b1", "name": "Marc Anthony"}]}]}}
        handler = self._server(tree, lambda fid: by_folder[fid],
                               folders=[{"id": 1, "name": "Bachata"}, {"id": 2, "name": "Salsa"}])
        rows = self.sync(handler)
        self.assertEqual(rows["x1"]["folder"], "Bachata/Aventura")
        self.assertEqual(rows["x2"]["folder"], "Salsa/Marc Anthony")

    def test_client_adapts_to_an_older_server_protocol(self):
        seen = []

        def handler(request):
            version = parse_qs(request.url.query.decode())["v"][0]
            seen.append(version)
            if version != "1.15.0":
                return httpx.Response(200, json={"subsonic-response": {"status": "failed", "version": "1.15.0",
                                                                          "error": {"code": 30, "message": "Server must upgrade"}}})
            return httpx.Response(200, json={"subsonic-response": {"status": "ok", "version": "1.15.0"}})

        async def go():
            client = self.make_client(handler)
            client.api_version = "1.16.1"          # what a newer default would send
            try:
                return await client.ping(), client.api_version
            finally:
                await client.aclose()

        self.assertEqual(self.run_async(go()), ("1.15.0", "1.15.0"))
        self.assertEqual(seen, ["1.16.1", "1.15.0"])

    def test_password_fallback_when_the_server_cannot_check_tokens(self):
        """Airsonic-Advanced with hashed passwords answers 41 to tokens and wants p=enc:<hex>."""
        seen = []

        def handler(request):
            q = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
            seen.append(q)
            if "t" in q:
                return httpx.Response(200, json={"subsonic-response": {"status": "failed", "version": "1.15.0", "error": {
                    "code": 41, "message": "Wrong username or password, but try authenticating via non-hashed password."}}})
            if q.get("p") == "enc:" + "s3cret-pass!".encode().hex():
                return httpx.Response(200, json={"subsonic-response": {"status": "ok", "version": "1.15.0"}})
            return httpx.Response(200, json={"subsonic-response": {"status": "failed", "error": {"code": 40, "message": "Wrong username or password"}}})

        async def go(password, **kw):
            client = AirsonicClient("https://x.example", "alice", password, transport=httpx.MockTransport(handler), **kw)
            try:
                await client.ping()
                return client
            finally:
                await client.aclose()

        client = self.run_async(go("s3cret-pass!"))
        self.assertEqual(client.auth_mode, "password")
        self.assertIn("t", seen[0])                       # tried the token first
        self.assertNotIn("t", seen[-1])                   # then switched
        self.assertNotIn("s", seen[-1])
        self.assertNotIn("s3cret-pass!", str(seen[-1]))       # never the bare password in the URL
        url = client.stream_url("9")                      # stream URLs must use the same mode
        self.assertIn("p=enc%3A", url)
        self.assertNotIn("&t=", url)
        # a remembered mode skips the failing token round trip
        seen.clear()
        again = self.run_async(go("s3cret-pass!", auth="password"))
        self.assertEqual(len(seen), 1)
        self.assertEqual(again.auth_mode, "password")
        # a genuinely wrong password still fails with the server's own answer
        with self.assertRaises(AirsonicError) as ctx:
            self.run_async(go("nope"))
        self.assertEqual(ctx.exception.code, 40)
        # forcing token mode never falls back
        with self.assertRaises(AirsonicError) as ctx:
            self.run_async(go("s3cret-pass!", auth="token"))
        self.assertEqual(ctx.exception.code, 41)

    def test_songs_carry_their_server_folder(self):
        self.assertEqual(song_to_row({"id": 1, "path": "Rock/Band One/Album A/01 Song.mp3"})["folder"], "Rock/Band One/Album A")
        self.assertEqual(song_to_row({"id": 2, "path": "Loose.mp3"})["folder"], "")
        self.assertEqual(song_to_row({"id": 3, "path": "A\\B\\c.flac"})["folder"], "A/B")
        self.assertEqual(song_to_row({"id": 4})["folder"], "")

    def test_stream_url_is_direct_and_authenticated(self):
        client = self.make_client(lambda r: httpx.Response(200))
        url = client.stream_url("42")
        parsed = urlparse(url)
        self.assertTrue(url.startswith("http://music.local:4040/rest/stream.view?"))
        query = parse_qs(parsed.query)
        self.assertEqual(query["id"], ["42"])
        self.assertIn("t", query)
        self.assertNotEqual(query["s"], parse_qs(urlparse(client.stream_url("42")).query)["s"])  # fresh salt each call

    def test_scrobble_sends_submission(self):
        seen = {}

        def handler(request):
            seen.update({k: v[0] for k, v in parse_qs(request.url.query.decode()).items()})
            seen["path"] = request.url.path
            return httpx.Response(200, json={"subsonic-response": {"status": "ok"}})

        async def go():
            client = self.make_client(handler)
            try:
                await client.scrobble("7")
            finally:
                await client.aclose()

        self.run_async(go())
        self.assertTrue(seen["path"].endswith("scrobble.view"))
        self.assertEqual((seen["id"], seen["submission"]), ("7", "true"))


def write_wav(path: Path, seconds=1.0, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(n)))


class IndexerTests(unittest.TestCase):
    def test_read_write_tags_roundtrip_and_walk(self):
        folder = Path(helpers.ROOT) / "music" / "sub"
        folder.mkdir(parents=True)
        wav = folder / "tone.wav"
        write_wav(wav, 1.5)
        (folder / "notes.txt").write_text("ignore me")
        tags = read_tags(wav)
        self.assertEqual(tags["title"], "tone")          # falls back to the file name
        self.assertAlmostEqual(tags["duration"], 1.5, places=1)
        write_tags(wav, {"title": "Tone A", "artist": "Tester", "album": "Sines", "genre": "Test", "year": 2024, "track_no": 3})
        tags = read_tags(wav)
        self.assertEqual((tags["title"], tags["artist"], tags["album"], tags["genre"], tags["year"], tags["track_no"]),
                         ("Tone A", "Tester", "Sines", "Test", 2024, 3))
        found = list(iter_audio_files([str(folder.parent)]))
        self.assertEqual([Path(p).name for p, _, _ in found], ["tone.wav"])

    def test_unreadable_file_is_skipped(self):
        bad = Path(helpers.ROOT) / "bad.mp3"
        bad.write_bytes(b"not audio at all")
        self.assertIsNone(read_tags(bad))


class LocaleTests(unittest.TestCase):
    def test_same_keys_and_placeholders(self):
        self.assertEqual(set(en.STRINGS), set(es.STRINGS))
        for key in en.STRINGS:
            self.assertEqual(set(re.findall(r"\{(\w+)\}", en.STRINGS[key])), set(re.findall(r"\{(\w+)\}", es.STRINGS[key])), key)

    def test_every_key_used_in_code_exists(self):
        root = Path(__file__).resolve().parent.parent / "juke"
        used = set()
        for path in root.rglob("*.py"):
            if "locales" in path.parts:
                continue
            used |= set(re.findall(r"""\btrn?\(\s*["']([A-Za-z_.]+)["']""", path.read_text()))
        missing = []
        for key in used:
            if key.endswith((".", "_")):
                continue  # dynamic prefix such as "col." / "eq.preset." / "unknown_"
            candidates = {key, key + "_one", key + "_other"}
            if not candidates & set(en.STRINGS):
                missing.append(key)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
