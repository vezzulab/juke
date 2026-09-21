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
            self.assertEqual(request.url.params["track_name"], "Blue Hour")
            return httpx.Response(200, json=[
                {"trackName": "Blue Hour", "artistName": "Ada", "albumName": "Paper", "duration": 201.4, "plainLyrics": "a\nb", "syncedLyrics": LRC},
                {"trackName": "Blue Hour", "artistName": "Ada", "instrumental": True},
                {"trackName": "Blue Hour", "artistName": "Bo", "plainLyrics": "words only", "syncedLyrics": None}])

        found = asyncio.run(lyrics.search("Blue Hour", "Ada", transport=httpx.MockTransport(handler)))
        self.assertEqual([(f.artist, f.is_synced) for f in found], [("Ada", True), ("Bo", False)])
        self.assertEqual(found[1].text, "words only")

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
