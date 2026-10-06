import json
import unittest
from pathlib import Path

from . import helpers  # noqa: F401  (sets XDG env, and keeps tests off the desktop's bus)

from PySide6.QtWidgets import QApplication, QMenu

from juke.audio.equalizer import BUILTIN_PRESETS, Equalizer, headroom
from juke.config import Config
from juke.i18n import translator

app = QApplication.instance() or QApplication([])


def make_eq(name):
    return Equalizer(Config(Path(helpers.ROOT) / f"{name}.json"))


class SongEqualizerTests(unittest.TestCase):
    def test_a_song_with_its_own_curve_plays_it_and_the_general_one_comes_back(self):
        eq = make_eq("song-eq-1")
        eq.set_enabled(False)
        eq.set_band(0, 3.0)
        general = (eq.enabled, eq.preamp, list(eq.gains))
        eq.begin_song(7, eq.curve_for("Rock"))
        self.assertEqual(eq.song_id, 7)
        self.assertTrue(eq.enabled)                                             # a song with a curve is shaped by it
        self.assertEqual(eq.gains, list(map(float, BUILTIN_PRESETS["Rock"])))
        self.assertEqual(eq.preamp, headroom(BUILTIN_PRESETS["Rock"]))
        eq.begin_song(8, None)                                                  # the next song has none
        self.assertIsNone(eq.song_id)
        self.assertEqual((eq.enabled, eq.preamp, list(eq.gains)), general)      # the general equalizer is exactly as it was

    def test_editing_while_a_song_has_its_own_curve_edits_that_song_only(self):
        eq = make_eq("song-eq-2")
        saved = []
        eq.song_saver = lambda song, curve: saved.append((song, curve))
        eq.set_band(1, 2.0)
        general_gains = list(eq.gains)
        stored_general = Config(Path(helpers.ROOT) / "song-eq-2.json").get("equalizer")["gains"]
        eq.begin_song(5, eq.curve_for("Jazz"))
        eq.set_band(3, 6.0)                                                     # the person moves a bar
        self.assertEqual(saved[-1][0], 5)                                       # ...it is kept with the song
        self.assertEqual(saved[-1][1]["gains"][3], 6.0)
        self.assertEqual(Config(Path(helpers.ROOT) / "song-eq-2.json").get("equalizer")["gains"], stored_general)   # the general one is untouched
        eq.end_song()
        self.assertEqual(eq.gains, general_gains)

    def test_going_back_to_the_general_equalizer_for_the_playing_song(self):
        eq = make_eq("song-eq-3")
        cleared = []
        eq.song_cleared.connect(cleared.append)
        eq.begin_song(9, eq.curve_for("Salsa"))
        eq.clear_song()
        self.assertEqual(cleared, [9])
        self.assertIsNone(eq.song_id)

    def test_a_saved_curve_is_read_back_and_nonsense_is_ignored(self):
        eq = make_eq("song-eq-4")
        curve = eq.curve_for("Pop")
        self.assertEqual(eq.parse_curve(json.dumps(curve))["gains"], curve["gains"])
        for bad in ("", "not json", "{}", json.dumps({"gains": [1, 2, 3]}), "[]"):
            self.assertIsNone(eq.parse_curve(bad), bad)
        self.assertIsNone(eq.curve_for("No such preset"))


class SongEqualizerWindowTests(unittest.TestCase):
    def setUp(self):
        translator.set_language("en")

    def test_a_group_of_songs_gets_one_curve_and_each_plays_with_it(self):
        from .test_gui import make_window, pump

        window, cfg, db, engine, eq = make_window("song-eq-win", n=6)
        window.resolver.resolve = lambda t: "file:///fake.mp3"
        engine.play_url = lambda url, fade=False: True
        ids = db.query_ids()
        window._song_eq_chosen(ids[:3], "preset:Dembow")                        # a group at once
        self.assertEqual([bool(db.get_track(i).eq) for i in ids], [True, True, True, False, False, False])
        self.assertIn("3 songs now have their own equalizer", window.statusBar().currentMessage())
        window._start(ids[1])                                                   # one of them plays: its curve is in
        self.assertEqual(eq.song_id, ids[1])
        self.assertEqual(eq.preset, "Dembow")
        window._start(ids[4])                                                   # one without: the general equalizer again
        self.assertIsNone(eq.song_id)
        window._song_eq_chosen([ids[1]], "")                                    # back to general for one of the group
        self.assertEqual(db.get_track(ids[1]).eq, "")
        self.assertTrue(db.get_track(ids[0]).eq)
        window._start(ids[0])
        eq.set_band(2, 5.5)                                                     # editing the playing song edits its own curve
        self.assertEqual(json.loads(db.get_track(ids[0]).eq)["gains"][2], 5.5)
        eq.clear_song()                                                         # "use the general equalizer" in the dialog
        self.assertEqual(db.get_track(ids[0]).eq, "")
        window.close()

    def test_changing_the_curve_of_the_song_that_plays_takes_effect_at_once(self):
        from .test_gui import make_window

        window, cfg, db, engine, eq = make_window("song-eq-live", n=3)
        window.resolver.resolve = lambda t: "file:///fake.mp3"
        engine.play_url = lambda url, fade=False: True
        ids = db.query_ids()
        window._start(ids[0])
        self.assertIsNone(eq.song_id)
        window._song_eq_chosen([ids[0]], "preset:Rock")                         # (chosen from the menu while it plays)
        self.assertEqual(eq.song_id, ids[0])
        window._song_eq_chosen([ids[0]], "")
        self.assertIsNone(eq.song_id)
        window.close()

    def test_the_context_menu_offers_it_and_marks_what_the_songs_have(self):
        from .test_gui import make_window

        window, cfg, db, engine, eq = make_window("song-eq-menu", n=4)
        ids = db.query_ids()
        window._song_eq_chosen(ids[:2], "preset:Salsa")
        table = window.table
        tracks = db.tracks_by_ids(ids[:2])
        menu = QMenu()
        table._add_eq_menu(menu, ids[:2], tracks)
        sub = menu.actions()[0].menu()
        self.assertEqual(menu.actions()[0].text(), "Equalizer for these 2 songs")
        labels = [a.text() for a in sub.actions() if a.text()]
        self.assertIn("General equalizer (default)", labels)                    # not ticked: both have their own
        presets = [a for a in sub.actions() if a.menu() is not None][0].menu()
        ticked = [a.text() for a in presets.actions() if a.text().startswith("✓")]
        self.assertEqual(ticked, ["✓  Salsa"])
        menu2 = QMenu()
        table._add_eq_menu(menu2, ids[2:3], db.tracks_by_ids(ids[2:3]))          # one without: the default is ticked
        self.assertEqual(menu2.actions()[0].text(), "Equalizer for this song")
        self.assertTrue(menu2.actions()[0].menu().actions()[0].text().startswith("✓"))
        window.close()

    def test_the_dialog_says_when_a_song_has_its_own_and_offers_the_way_back(self):
        from juke.audio.engine import AudioEngine
        from juke.gui.components.eq_dialog import EqualizerDialog

        eq = make_eq("song-eq-dialog")
        dialog = EqualizerDialog(eq, AudioEngine())
        dialog.show()
        self.assertFalse(dialog.song_bar.isVisible())
        eq.begin_song(3, eq.curve_for("Rock"))
        self.assertTrue(dialog.song_bar.isVisible())
        self.assertFalse(dialog.enabled.isEnabled())
        self.assertIn("Rock", dialog.song_note.text())
        dialog.song_back.click()
        self.assertFalse(dialog.song_bar.isVisible())
        self.assertTrue(dialog.enabled.isEnabled())


if __name__ == "__main__":
    unittest.main()
