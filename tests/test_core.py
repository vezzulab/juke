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

    def test_sync_walks_indexes_and_directories(self):
        tree = {
            "ar1": {"child": [{"id": "al1", "isDir": True}, {"id": "s3", "title": "Loose", "artist": "A1"}]},
            "al1": {"child": [{"id": "s1", "title": "One", "artist": "A1", "album": "Al", "duration": 61, "bitRate": 256,
                               "coverArt": "al1", "track": 1, "year": 1999, "genre": "Pop"},
                              {"id": "s2", "title": "Two", "artist": "A1", "album": "Al"}]},
            "ar2": {"child": {"id": "s4", "title": "Single dict child"}},
        }

        def handler(request):
            params = parse_qs(request.url.query.decode())
            path = request.url.path
            if path.endswith("getIndexes.view"):
                body = {"indexes": {"index": [{"name": "A", "artist": [{"id": "ar1"}, {"id": "ar2"}]}], "child": [{"id": "s0", "title": "Root song"}]}}
            else:
                body = {"directory": tree[params["id"][0]]}
            return httpx.Response(200, json={"subsonic-response": {"status": "ok", **body}})

        async def go():
            client = self.make_client(handler)
            try:
                return await client.sync_library()
            finally:
                await client.aclose()

        rows = self.run_async(go())
        self.assertEqual(sorted(r["location"] for r in rows), ["s0", "s1", "s2", "s3", "s4"])
        one = next(r for r in rows if r["location"] == "s1")
        self.assertEqual((one["title"], one["duration"], one["bitrate"], one["cover_key"], one["source_type"]),
                         ("One", 61.0, 256, "as_al1", "airsonic"))

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
