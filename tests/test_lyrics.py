import asyncio
import unittest
from pathlib import Path

from . import helpers  # noqa: F401  (sets XDG env first)

from juke import lyrics
from juke.db.database import Database
from juke.i18n import translator

from .test_core import row

LRC = "[ar:Somebody]\n[00:01.50] First line\n[00:05.00]Second line\n[00:09.25] Third line\n"


class LyricsCoreTests(unittest.TestCase):
    def test_lrc_is_read_in_time_order_and_headers_are_ignored(self):
        self.assertEqual(lyrics.parse_lrc(LRC), [(1500, "First line"), (5000, "Second line"), (9250, "Third line")])
        self.assertTrue(lyrics.is_synced(LRC))
        self.assertFalse(lyrics.is_synced("just words\nno times"))
        self.assertEqual(lyrics.plain_text(LRC), "First line\nSecond line\nThird line")
        self.assertEqual(lyrics.parse_lrc("[00:10.0][00:20.0] chorus"), [(10000, "chorus"), (20000, "chorus")])   # a repeated line

    def test_the_line_being_sung(self):
        timeline = lyrics.parse_lrc(LRC)
        self.assertEqual([lyrics.line_at(timeline, ms) for ms in (0, 1499, 1500, 6000, 99999)], [-1, -1, 0, 1, 2])

    def test_a_lrc_beside_the_song_is_found(self):
        import tempfile
        folder = Path(tempfile.mkdtemp(prefix="juke-lyrics-"))
        (folder / "song.mp3").write_bytes(b"x")
        self.assertEqual(lyrics.local_lyrics(str(folder / "song.mp3")), "")
        (folder / "song.lrc").write_text(LRC, encoding="utf-8")
        self.assertIn("First line", lyrics.local_lyrics(str(folder / "song.mp3")))

    def test_lrclib_results_are_read_and_instrumentals_skipped(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            if "lrclib" not in request.url.host:
                return httpx.Response(404)                          # the other services know nothing of this song
            self.assertIn("Blue Hour", request.url.params.get("track_name") or request.url.params.get("q"))
            return httpx.Response(200, json=[
                {"trackName": "Blue Hour", "artistName": "Ada", "albumName": "Paper", "duration": 201.4, "plainLyrics": "a\nb", "syncedLyrics": LRC},
                {"trackName": "Blue Hour", "artistName": "Ada", "instrumental": True},
                {"trackName": "Blue Hour", "artistName": "Bo", "plainLyrics": "words only", "syncedLyrics": None}])

        found = asyncio.run(lyrics.search("Blue Hour", "Ada", transport=httpx.MockTransport(handler)))
        self.assertEqual([(f.artist, f.is_synced) for f in found], [("Ada", True), ("Bo", False)])
        self.assertEqual(found[1].text, "words only")

    def test_other_languages_are_found_and_titles_are_cleaned(self):
        import httpx

        self.assertEqual(lyrics.clean_title("03 - Despacito (feat. Daddy Yankee) [Remastered 2017]"), "Despacito")
        self.assertEqual(lyrics.clean_title("夜曲 - Live"), "夜曲")
        self.assertEqual(lyrics.main_artist("周杰伦 & 方文山"), "周杰伦")

        def handler(request: httpx.Request) -> httpx.Response:
            host = request.url.host
            if "lrclib" in host:
                return httpx.Response(404)
            if "163.com" in host and request.url.path.endswith("/search/get"):
                return httpx.Response(200, json={"result": {"songs": [
                    {"id": 7, "name": "夜曲", "artists": [{"name": "周杰伦"}], "album": {"name": "十一月的萧邦"}, "duration": 226000}]}})
            if "163.com" in host:
                return httpx.Response(200, json={"lrc": {"lyric": "[00:00.00] 作词 : 方文山\n[00:20.00]一群嗜血的蚂蚁\n[00:25.00]被腐肉所吸引"}})
            return httpx.Response(404)

        found = asyncio.run(lyrics.search("夜曲", "周杰伦", transport=httpx.MockTransport(handler)))
        self.assertEqual([(f.source, f.is_synced) for f in found], [("NetEase", True)])
        self.assertNotIn("作词", found[0].synced)                                   # credits are not lyrics
        self.assertIn("嗜血", lyrics.plain_text(found[0].text))

    def test_a_busy_service_is_asked_again_and_other_songs_are_not_offered(self):
        import httpx

        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if "lrclib" not in request.url.host:
                return httpx.Response(404)
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(503, json={"message": "The server is busy, please retry in a moment"})
            return httpx.Response(200, json=[
                {"trackName": "La Cabra Y La Soga", "artistName": "Frankie Ruiz", "plainLyrics": "words", "syncedLyrics": None, "duration": 250},
                {"trackName": "Derroche", "artistName": "Orquesta La Solución", "plainLyrics": "other song", "syncedLyrics": LRC}])

        import asyncio as aio
        orig = aio.sleep

        async def quick(_seconds):
            return None

        lyrics.asyncio.sleep = quick
        try:
            found = asyncio.run(lyrics.search("La Cabra Y La Soga", "Orquesta La Solucion", transport=httpx.MockTransport(handler)))
        finally:
            lyrics.asyncio.sleep = orig
        self.assertGreater(calls["n"], 1)                                            # it asked again after the 503
        self.assertEqual([(f.title, f.artist) for f in found], [("La Cabra Y La Soga", "Frankie Ruiz")])   # the cover, not "Derroche"

    def test_artist_dash_song_in_the_title_box_and_other_spellings_of_a_group(self):
        self.assertEqual(lyrics._variants("orquesta la solucion - Ruina", "")[0], ("Ruina", "orquesta la solucion"))
        self.assertEqual(lyrics._variants("RICHIE RAY & BOBBY CRUZ - Aguzate", "Richie Ray")[0], ("Aguzate", "Richie Ray"))
        self.assertEqual(lyrics._variants("La Ruina", "Orquesta La Solucion"), [("La Ruina", "Orquesta La Solucion")])
        self.assertEqual(lyrics.artist_core("Orquesta La Solucion"), "Solucion")
        found = lyrics.Found("La Ruina", "La Solución", "", 0, "x", "")                 # the group under its other spelling
        self.assertGreater(lyrics.relevance(found, "La Ruina", "Orquesta La Solucion")[1], 0.9)

    def test_everything_down_says_who_did_not_answer(self):
        import httpx

        async def run():
            async def quick(_s):
                return None

            orig, lyrics.asyncio.sleep = lyrics.asyncio.sleep, quick
            try:
                return await lyrics.search_report("Ruina", "Orquesta La Solucion",
                                                  transport=httpx.MockTransport(lambda r: httpx.Response(503)))
            finally:
                lyrics.asyncio.sleep = orig

        report = asyncio.run(run())
        self.assertEqual(report.found, [])
        self.assertIn("LRCLIB", report.failed)

    def test_accents_and_case_do_not_hide_a_match(self):
        found = lyrics.Found("Una Cañita Más", "Orquesta La Solución", "", 0, "x", "")
        self.assertGreater(lyrics.relevance(found, "UNA CANITA MAS", "Orquesta La Solucion")[1], 0.95)

    def test_old_lyric_files_in_other_encodings_are_read(self):
        for text, encoding in (("[00:01.00]你好 世界\n[00:05.00]再见 朋友", "gb18030"),
                               ("[00:01.00]こんにちは世界\n[00:05.00]さようなら", "shift_jis"),
                               ("[00:01.00]안녕하세요 세계\n[00:05.00]사랑해요", "euc_kr"),
                               ("canción de amor ñandú", "cp1252"), ("日本語の歌", "utf-16")):
            self.assertEqual(lyrics.decode_text(text.encode(encoding)), text, encoding)

    def test_no_match_is_not_an_error(self):
        import httpx
        self.assertIsNone(asyncio.run(lyrics.get_exact("x", "y", "z", 100, transport=httpx.MockTransport(lambda r: httpx.Response(404)))))


class LyricsStorageTests(unittest.TestCase):
    def test_lyrics_belong_to_the_song_and_survive_a_rescan(self):
        import tempfile
        db = Database(Path(tempfile.mkdtemp(prefix="juke-lyrics-db-")) / "lib.db")
        db.upsert_many([row(1, location="/music/a.mp3")])
        track = db.find_by_location("local", "/music/a.mp3")
        self.assertEqual(db.get_lyrics(track), "")
        db.set_lyrics(track, "  la la la  ")
        self.assertEqual(db.get_lyrics(track), "la la la")
        db.upsert_many([row(1, location="/music/a.mp3", title="renamed")])          # a rescan rewrites the row, not the lyrics
        self.assertEqual(db.get_lyrics(db.find_by_location("local", "/music/a.mp3")), "la la la")
        db.set_lyrics(track, "")
        self.assertEqual(db.get_lyrics(track), "")


class LyricsPanelTests(unittest.TestCase):
    def test_the_panel_follows_a_synced_song_and_shows_an_invitation_when_empty(self):
        from PySide6.QtWidgets import QApplication
        translator.set_language("en")
        QApplication.instance() or QApplication([])
        from juke.gui.components.lyrics_panel import LyricsPanel

        panel = LyricsPanel()
        panel.set_lyrics("")
        self.assertFalse(panel.has_lyrics)                                            # the invitation, not an empty box
        panel.set_lyrics(LRC)
        self.assertTrue(panel.has_lyrics)
        self.assertEqual(panel.text.toPlainText(), "First line\nSecond line\nThird line")
        panel.set_position(6000)
        self.assertEqual(panel._current, 1)
        self.assertEqual(len(panel.text.extraSelections()), 1)
        panel.set_lyrics("plain words\nonly")
        panel.set_position(6000)
        self.assertEqual(panel.text.extraSelections(), [])                            # nothing to light up without times


if __name__ == "__main__":
    unittest.main()
