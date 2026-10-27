"""YouTube search: the ranking that keeps results exact, the database rules, and the window with a faked yt-dlp."""

import time
import unittest
from pathlib import Path
from unittest import mock

from . import helpers

from PySide6.QtCore import QCoreApplication

from juke.api import youtube
from juke.db.database import SOURCE_YOUTUBE, Database, Scope

from .test_core import row
from .test_gui import make_window, pump


def item(video_id, title, channel, duration=240.0, views=1_000_000, verified=False):
    return {"video_id": video_id.ljust(11, "x")[:11], "title": title, "channel": channel, "duration": duration,
            "views": views, "verified": verified}


class ParseTests(unittest.TestCase):
    def test_channels_playlists_and_live_streams_are_not_songs(self):
        entries = [
            {"id": "abcdefghijk", "title": "A song", "channel": "Band", "duration": 200},
            {"id": "UCxxxxxxxxxxxxxxxxxxxxxx", "title": "A channel", "duration": 0},
            {"id": "abcdefghijk", "title": "A song again", "channel": "Band", "duration": 200},
            {"id": "livelivelive", "title": "Live", "duration": 100, "live_status": "is_live"},
            {"id": "elevenchars", "title": "No length", "duration": None},
            None,
        ]
        found = youtube.parse_results(entries)
        self.assertEqual([r["video_id"] for r in found], ["abcdefghijk"])


class ArtistTests(unittest.TestCase):
    def found(self, channel, n=6, cid="UC" + "a" * 22):
        return [{**item(f"s{i}", f"Song {i}", channel), "channel_id": cid} for i in range(n)]

    def test_the_name_of_an_artist_is_recognised_by_its_channel(self):
        self.assertEqual(youtube.artist_channel(self.found("Jossie Esteban TV"), "Jossie Esteban"), "UC" + "a" * 22)
        self.assertEqual(youtube.artist_channel(self.found("Juan Luis Guerra 4.40"), "juan luis guerra"), "UC" + "a" * 22)
        self.assertEqual(youtube.artist_channel(self.found("Romeo Santos - Topic"), "Romeo Santos"), "UC" + "a" * 22)

    def test_a_song_a_genre_or_somebody_else_is_not_an_artist(self):
        self.assertEqual(youtube.artist_channel(self.found("Juan Luis Guerra"), "burbujas de amor"), "")
        self.assertEqual(youtube.artist_channel(self.found("Juan Luis Guerra"), "juan luis guerra burbujas"), "")
        self.assertEqual(youtube.artist_channel(self.found("Salsa Mix Channel"), "salsa"), "")
        self.assertEqual(youtube.artist_channel(self.found("Karen Records"), "juan luis guerra"), "")
        self.assertEqual(youtube.artist_channel(self.found("Juan Luis Guerra", n=1), "juan luis guerra"), "")   # one hit proves nothing

    def test_an_artist_search_lists_the_whole_repertoire(self):
        cid = "UC" + "a" * 22
        searched = [{"id": f"{i:011d}", "title": f"Juan Luis Guerra - Song {i}", "channel": "Juan Luis Guerra", "channel_id": cid,
                     "duration": 240, "view_count": 1000 + i} for i in range(8)]
        catalog = [{"id": f"{i:011d}", "title": f"Song {i}", "channel": "Juan Luis Guerra", "channel_id": cid,
                    "duration": 240, "view_count": 5_000_000 - i} for i in range(5, 80)]
        catalog.append({"id": "book0000000", "title": "Captain Avispa's Book", "channel": "Juan Luis Guerra", "channel_id": cid, "duration": 200})
        modes = []

        def helper(mode, text):
            modes.append(mode)
            return {"entries": searched if mode == "search" else catalog}

        with mock.patch.object(youtube, "_helper", helper):
            ranked = youtube.search("juan luis guerra")
        self.assertEqual(modes, ["search", "channel"])
        self.assertEqual(len(ranked), 80)                                  # the 20 of a normal search would cut it short
        self.assertNotIn("Captain Avispa's Book", [r["title"] for r in ranked])
        self.assertEqual(len({r["video_id"] for r in ranked}), 80)

    def test_a_song_search_does_not_ask_for_a_catalog(self):
        modes = []

        def helper(mode, text):
            modes.append(mode)
            return {"entries": [{"id": "abcdefghijk", "title": "Burbujas de Amor", "channel": "Juan Luis Guerra", "channel_id": "UC" + "a" * 22, "duration": 240}] * 3}

        with mock.patch.object(youtube, "_helper", helper):
            youtube.search("burbujas de amor")
        self.assertEqual(modes, ["search"])


class UpdateTests(unittest.TestCase):
    """yt-dlp is fixed within days of YouTube changing: Juke fetches the newer one by itself."""

    def wheel(self, version="2099.01.01", extra=True):
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("yt_dlp/__init__.py", "")
            z.writestr("yt_dlp/version.py", f"__version__ = '{version}'\n")
            if extra:
                z.writestr("../evil.py", "x = 1")
                z.writestr("yt_dlp-%s.dist-info/METADATA" % version, "")
        return buffer.getvalue()

    def test_a_wheel_is_checked_and_unpacked_where_the_helper_will_find_it(self):
        import hashlib
        import tempfile

        data = self.wheel()
        target = Path(tempfile.mkdtemp()) / "yt-dlp"
        with self.assertRaises(ValueError):
            youtube.install_wheel(data, "0" * 64, target)                       # not what PyPI said it was
        self.assertFalse(target.exists())
        youtube.install_wheel(data, hashlib.sha256(data).hexdigest(), target)
        self.assertEqual((target / "yt_dlp" / "version.py").read_text().strip(), "__version__ = '2099.01.01'")
        self.assertFalse((target.parent / "evil.py").exists())                  # nothing outside yt_dlp/ is written
        with self.assertRaises(ValueError):
            youtube.install_wheel(b"not a zip", "", target)

    def test_it_updates_only_when_pypi_has_something_newer(self):
        import hashlib
        import json
        import tempfile

        data = self.wheel()
        root = Path(tempfile.mkdtemp())
        pypi = json.dumps({"info": {"version": "2099.01.01"}, "urls": [
            {"packagetype": "bdist_wheel", "filename": "yt_dlp-2099.01.01-py3-none-any.whl", "url": "https://files/x.whl",
             "digests": {"sha256": hashlib.sha256(data).hexdigest()}}]}).encode()

        def fetch(url, limit):
            return pypi if "pypi.org" in url else data

        with mock.patch.object(youtube, "YTDLP_DIR", root / "yt-dlp"), mock.patch.object(youtube, "YTDLP_STATE", root / "state.json"), \
                mock.patch.object(youtube, "_fetch", fetch):
            with mock.patch.object(youtube, "installed_version", return_value="2099.01.01"):
                self.assertEqual(youtube.update_ytdlp(force=True), "2099.01.01")      # already the newest: nothing is downloaded
                self.assertFalse((root / "yt-dlp").exists())
            with mock.patch.object(youtube, "installed_version", return_value="2026.10.21"):
                self.assertEqual(youtube.update_ytdlp(force=True), "2099.01.01")
                self.assertTrue((root / "yt-dlp" / "yt_dlp" / "version.py").is_file())
                self.assertEqual(youtube._env()["JUKE_YTDLP_DIR"], str(root / "yt-dlp"))
                self.assertEqual(youtube.update_ytdlp(), "2099.01.01")                # asked again soon: it does not ask PyPI again

    def test_an_answer_that_means_youtube_changed_looks_for_a_fix_and_tries_again(self):
        calls = []

        def helper(mode, text):
            calls.append(mode)
            if len([c for c in calls if c == "search"]) == 1:
                raise youtube.YouTubeError("unavailable", "Unable to extract uploader id")
            return {"entries": []}

        with mock.patch.object(youtube, "_helper", helper), mock.patch.object(youtube, "installed_version", side_effect=["old"]), \
                mock.patch.object(youtube, "update_ytdlp", return_value="new"):
            self.assertEqual(youtube._helper_fixing("search", "x"), {"entries": []})
        self.assertEqual(calls, ["search", "search"])
        with mock.patch.object(youtube, "_helper", side_effect=youtube.YouTubeError("network", "timeout")):
            with self.assertRaises(youtube.YouTubeError):
                youtube._helper_fixing("search", "x")                                 # no connection is not YouTube changing

    def test_without_a_fix_the_error_is_the_error(self):
        with mock.patch.object(youtube, "_helper", side_effect=youtube.YouTubeError("unavailable", "Unable to extract x")), \
                mock.patch.object(youtube, "installed_version", return_value="same"), mock.patch.object(youtube, "update_ytdlp", return_value="same"):
            with self.assertRaises(youtube.YouTubeError):
                youtube._helper_fixing("stream", "abcdefghijk")


class RankTests(unittest.TestCase):
    def test_only_the_artist_that_was_searched_comes_back(self):
        results = [
            item("a", "Bachata en Fukuoka", "Otro Artista", views=900_000_000),
            item("b", "Juan Luis Guerra - Mi Bendición", "Juan Luis Guerra", verified=True),
            item("c", "Juan Luis Guerra - Burbujas de Amor", "Juan Luis Guerra", verified=True),
            item("d", "Juan Luis Guerra 4.40 - Ojalá Que Llueva Café", "Karen Records"),
            item("e", "Romeo Santos - Propuesta Indecente", "Romeo Santos"),
        ]
        ranked = youtube.rank(results, "juan luis guerra")
        self.assertEqual({r["video_id"][0] for r in ranked}, {"b", "c", "d"})

    def test_accents_and_case_do_not_matter(self):
        results = [item("a", "JOSSIE ESTEBAN - El Cantinero", "Jossie Esteban TV"),
                   item("b", "Jossie Estéban - Un Hombre Busca Una Mujer", "Jossie Esteban TV"),
                   item("c", "Jossie Esteban - Oho Aha", "Jossie Esteban TV"),
                   item("d", "Someone Else", "Nobody")]
        ranked = youtube.rank(results, "jossié esteban")
        self.assertEqual(len(ranked), 3)

    def test_mixes_albums_and_covers_are_left_out_unless_asked_for(self):
        results = [
            item("a", "Merengue Mix 2026 - Exitos", "DJ Uno", duration=3000),
            item("b", "Elvis Crespo - Suavemente", "Elvis Crespo", verified=True),
            item("c", "Suavemente (Cover) Merengue", "Un Fan"),
            item("d", "Merengue clasico - Full Album", "Disquera", duration=3000),
            item("e", "Merengue de Oro - Wilfrido Vargas", "Wilfrido", verified=True),
            item("f", "Merengue Karaoke Fiesta", "Karaoke Co"),
            item("g", "Merengue - Fulanito - Guallando", "Fulanito"),
        ]
        ranked = [r["video_id"][0] for r in youtube.rank(results, "merengue")]
        self.assertNotIn("a", ranked)
        self.assertNotIn("d", ranked)
        self.assertNotIn("f", ranked)
        self.assertIn("b", ranked)
        self.assertNotIn("c", ranked)
        asked = [r["video_id"][0] for r in youtube.rank(results, "merengue mix")]
        self.assertIn("a", asked)

    def test_live_versions_only_when_asked(self):
        results = [item("a", "La Bilirrubina (Live)", "Juan Luis Guerra", views=50_000_000),
                   item("b", "La Bilirrubina", "Juan Luis Guerra", views=45_000_000)]
        self.assertEqual(youtube.rank(results, "la bilirrubina")[0]["video_id"][0], "b")
        self.assertEqual(youtube.rank(results, "la bilirrubina en vivo")[0]["video_id"][0], "a")

    def test_the_original_beats_a_reupload(self):
        results = [item("a", "Juan Luis Guerra - La Bilirrubina (Video Clip)", "Marcos", views=100_000),
                   item("b", "La Bilirrubina", "Juan Luis Guerra", views=45_000_000, verified=True)]
        self.assertEqual(youtube.rank(results, "la bilirrubina")[0]["video_id"][0], "b")

    def test_a_song_listed_twice_is_shown_once(self):
        results = [item("a", "Mi Bendición", "Juan Luis Guerra"),
                   item("b", "Mi Bendición (Official Audio)", "Juan Luis Guerra - Topic"),
                   item("c", "Burbujas de Amor", "Juan Luis Guerra")]
        titles = [r["title"] for r in youtube.rank(results, "juan luis guerra")]
        self.assertEqual(len([t for t in titles if "Bendición" in t]), 1)

    def test_recipes_are_not_music(self):
        results = [item("a", "Salsa Roja Recipe from scratch", "Chef", views=900_000_000),
                   item("b", "Marc Anthony - Valió La Pena", "Marc Anthony"),
                   item("c", "Gilberto Santa Rosa - Conteo Regresivo", "Gilberto Santa Rosa"),
                   item("d", "Tito Nieves - Fabricando Fantasias", "Tito Nieves")]
        self.assertNotIn("a", [r["video_id"][0] for r in youtube.rank(results, "salsa")])


class AudioFirstTests(unittest.TestCase):
    def test_the_audio_version_beats_the_video_clip(self):
        results = [item("a", "Juan Luis Guerra - La Bilirrubina (Video Oficial)", "Juan Luis Guerra", views=90_000_000, verified=True),
                   item("b", "La Bilirrubina", "Juan Luis Guerra - Topic", views=2_000_000),
                   item("c", "Juan Luis Guerra - Burbujas de Amor (Official Audio)", "Juan Luis Guerra", views=1_000_000),
                   item("d", "Juan Luis Guerra - Burbujas de Amor (Official Video)", "Juan Luis Guerra", views=30_000_000, verified=True)]
        ranked = youtube.rank(results, "juan luis guerra")
        titles = [r["title"] for r in ranked]
        self.assertEqual(len([t for t in titles if "Burbujas" in t]), 1)
        self.assertIn("(Official Audio)", [t for t in titles if "Burbujas" in t][0])
        self.assertIn("La Bilirrubina", titles)                       # the audio is kept, its video clip is not listed
        self.assertNotIn("Juan Luis Guerra - La Bilirrubina (Video Oficial)", titles)

    def test_a_video_is_fine_when_it_is_asked_for(self):
        results = [item("a", "La Bilirrubina (Video Oficial)", "Juan Luis Guerra", views=90_000_000),
                   item("b", "La Bilirrubina (Official Audio)", "Juan Luis Guerra", views=1_000_000)]
        self.assertEqual(youtube.rank(results, "la bilirrubina video")[0]["video_id"][0], "a")

    def test_titles_lose_their_tags_and_the_artist_prefix(self):
        self.assertEqual(youtube.clean_title("Juan Luis Guerra 4.40 - Las Avispas (Video Oficial)", "Juan Luis Guerra"), "Las Avispas")
        self.assertEqual(youtube.clean_title("Mi Bendición [Official Audio] HD", "Juan Luis Guerra"), "Mi Bendición HD")
        self.assertEqual(youtube.clean_title("Romeo - Eres Mía (Remastered 2019)", "Aventura"), "Romeo - Eres Mía (Remastered 2019)")
        self.assertEqual(youtube.clean_title("(Official Video)", "X"), "(Official Video)")
        self.assertEqual(youtube.clean_channel("Arturo Sandoval - Topic"), "Arturo Sandoval")


class StreamTests(unittest.TestCase):
    def test_the_address_is_looked_up_once_and_then_remembered(self):
        youtube._cache.clear()
        with mock.patch.object(youtube, "_helper", return_value={"url": "https://example.test/audio"}) as helper:
            self.assertEqual(youtube.resolve_stream("abcdefghijk"), "https://example.test/audio")
            self.assertEqual(youtube.resolve_stream("abcdefghijk"), "https://example.test/audio")
        helper.assert_called_once_with("stream", "abcdefghijk")
        youtube.forget("abcdefghijk")
        self.assertNotIn("abcdefghijk", youtube._cache)

    def test_a_video_without_audio_is_unavailable(self):
        youtube._cache.clear()
        with mock.patch.object(youtube, "_helper", return_value={"url": ""}):
            with self.assertRaises(youtube.YouTubeError) as caught:
                youtube.resolve_stream("abcdefghijk")
        self.assertEqual(caught.exception.code, "unavailable")

    def test_what_the_helper_reports_becomes_a_youtube_error(self):
        class Done:
            stdout, stderr = '{"error": "Video unavailable"}', ""

        with mock.patch("subprocess.run", return_value=Done()):
            with self.assertRaises(youtube.YouTubeError) as caught:
                youtube._helper("stream", "abcdefghijk")
        self.assertEqual(caught.exception.code, "unavailable")

        Done.stdout = '{"missing": true}'
        with mock.patch("subprocess.run", return_value=Done()):
            with self.assertRaises(youtube.YouTubeError) as caught:
                youtube._helper("search", "x")
        self.assertEqual(caught.exception.code, "missing")

    def test_a_helper_that_hangs_is_a_network_error(self):
        import subprocess

        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 1)):
            with self.assertRaises(youtube.YouTubeError) as caught:
                youtube._helper("search", "x")
        self.assertEqual(caught.exception.code, "network")

    def test_juke_never_loads_yt_dlp_into_its_own_memory(self):
        import subprocess
        import sys

        code = "import sys; from juke.api import youtube; assert 'yt_dlp' not in sys.modules; print('clean')"
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))
        self.assertEqual(done.stdout.strip(), "clean", done.stderr)

    def test_the_helper_command_differs_when_bundled(self):
        self.assertIn("youtube_helper.py", youtube._command("search", "x")[2])
        with mock.patch.object(youtube.sys, "frozen", True, create=True):
            self.assertEqual(youtube._command("search", "x")[1:], ["--youtube-helper", "search", "x"])


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(Path(helpers.ROOT) / f"yt-{time.monotonic_ns()}.db")
        self.db.upsert_many([row(1, location="/music/1.mp3"), row(2, location="/music/2.mp3")])
        self.ids = self.db.upsert_youtube([
            {"video_id": "aaaaaaaaaaa", "title": "Song A", "channel": "Band", "duration": 200.0},
            {"video_id": "bbbbbbbbbbb", "title": "Song B", "channel": "Band", "duration": 210.0},
        ])

    def test_searched_songs_stay_out_of_the_library(self):
        self.assertEqual(self.db.count(), 2)
        self.assertEqual(len(self.db.query_ids(Scope())), 2)
        self.assertTrue(all(name != "Band" for name, _ in self.db.distinct("artist")))

    def test_but_they_are_found_when_asked_for(self):
        self.assertEqual(len(self.db.query_ids(Scope(source_type=SOURCE_YOUTUBE))), 2)
        self.assertEqual(len(self.db.query_ids(Scope(with_online=True))), 4)

    def test_a_second_search_keeps_the_same_ids(self):
        again = self.db.upsert_youtube([{"video_id": "aaaaaaaaaaa", "title": "Song A", "channel": "Band", "duration": 200.0}])
        self.assertEqual(again["aaaaaaaaaaa"], self.ids["aaaaaaaaaaa"])

    def test_favorites_show_them_and_cleanup_spares_what_is_kept(self):
        kept, playlisted, gone = self.ids["aaaaaaaaaaa"], self.ids["bbbbbbbbbbb"], None
        extra = self.db.upsert_youtube([{"video_id": "ccccccccccc", "title": "Song C", "channel": "Band", "duration": 1.0}])["ccccccccccc"]
        conn = self.db.connect()
        with conn:
            conn.execute("UPDATE tracks SET favorite=1 WHERE id=?", (kept,))
            conn.execute("UPDATE tracks SET added_at=1 WHERE source_type=?", (SOURCE_YOUTUBE,))
        self.assertIn(kept, self.db.query_ids(Scope(favorites=True)))
        playlist = self.db.create_playlist("Fiesta")
        self.db.add_to_playlist(playlist, [playlisted])
        self.assertEqual(self.db.cleanup_youtube(), 1)               # only the unkept one goes
        self.assertIsNone(self.db.get_track(extra))
        self.assertIsNotNone(self.db.get_track(kept))
        self.assertIsNotNone(self.db.get_track(playlisted))


class WindowTests(unittest.TestCase):
    def test_search_lists_results_and_a_playlist_keeps_them(self):
        window, cfg, db, engine, eq = make_window(f"yt-window-{time.monotonic_ns()}", n=5)
        found = [item("a", "Juan Luis Guerra - La Bilirrubina", "Juan Luis Guerra"),
                 item("b", "Juan Luis Guerra - Burbujas de Amor", "Juan Luis Guerra")]
        with mock.patch.object(youtube, "search", return_value=found):
            window._show_view("youtube", None)
            self.assertEqual(window.table.track_model.rowCount(), 0)
            window.search.setText("juan luis guerra")
            window._youtube_search()
            end = time.monotonic() + 5
            while window.table.track_model.rowCount() < 2 and time.monotonic() < end:
                pump(30)
        self.assertEqual(window.table.track_model.rowCount(), 2)
        ids = window._yt_ids
        playlist = db.create_playlist("Merengue")
        window._add_to_playlist(playlist, ids)
        window._show_view("all", None)
        self.assertEqual(window.table.track_model.rowCount(), 5)         # the library did not grow
        window._show_view("playlist", playlist)
        self.assertEqual(window.table.track_model.rowCount(), 2)         # the playlist plays from there, no new search
        window.close()

    def test_a_youtube_song_plays_through_the_resolved_address(self):
        window, cfg, db, engine, eq = make_window(f"yt-play-{time.monotonic_ns()}", n=2)
        by_video = db.upsert_youtube([{"video_id": "abcdefghijk", "title": "Song", "channel": "Band", "duration": 200.0}])
        track_id = by_video["abcdefghijk"]
        started = []
        window._begin = lambda track, url: started.append((track.id, url))
        with mock.patch.object(youtube, "resolve_stream", return_value="https://example.test/a.webm") as resolve:
            window._start(track_id)
            end = time.monotonic() + 5
            while not started and time.monotonic() < end:
                pump(30)
        resolve.assert_called_once_with("abcdefghijk")
        self.assertEqual(started, [(track_id, "https://example.test/a.webm")])
        window.close()

    def test_choosing_another_song_cancels_the_one_being_looked_up(self):
        window, cfg, db, engine, eq = make_window(f"yt-cancel-{time.monotonic_ns()}", n=2)
        track_id = db.upsert_youtube([{"video_id": "abcdefghijk", "title": "Song", "channel": "Band", "duration": 200.0}])["abcdefghijk"]
        started = []
        window._begin = lambda track, url: started.append(track.id)

        def slow(video_id):
            time.sleep(0.4)
            return "https://example.test/a.webm"

        with mock.patch.object(youtube, "resolve_stream", side_effect=slow):
            window._start(track_id)
            window._stop()
            pump(900)
        self.assertEqual(started, [])
        window.close()

    def test_a_failed_lookup_skips_with_a_message(self):
        window, cfg, db, engine, eq = make_window(f"yt-fail-{time.monotonic_ns()}", n=2)
        track_id = db.upsert_youtube([{"video_id": "abcdefghijk", "title": "Gone Song", "channel": "Band", "duration": 200.0}])["abcdefghijk"]
        with mock.patch.object(youtube, "resolve_stream", side_effect=youtube.YouTubeError("unavailable", "x")), \
                mock.patch.object(window, "_advance"):
            window._start(track_id)
            end = time.monotonic() + 5
            while "Gone Song" not in window.statusBar().currentMessage() and time.monotonic() < end:
                pump(30)
        self.assertIn("Gone Song", window.statusBar().currentMessage())
        window.close()


if __name__ == "__main__":
    unittest.main()
