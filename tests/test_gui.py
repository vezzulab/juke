"""Offscreen smoke tests of the real widgets, plus playback through libVLC when available."""

import time
import unittest
from pathlib import Path

from . import helpers

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from juke.audio.engine import AudioEngine
from juke.audio.equalizer import BUILTIN_PRESETS, Equalizer
from juke.config import Config
from juke.db.database import SOURCE_AIRSONIC, SOURCE_LOCAL, Database, Scope
import juke.gui.main_window as main_window_module
from juke.gui import icons, styles
from juke.gui.components.sidebar import COUNT_ROLE
from juke.gui.main_window import MainWindow
from juke.i18n import tr, translator

from .test_core import row, write_wav

app = QApplication.instance() or QApplication([])
app.setStyleSheet(styles.build_stylesheet())
app.setPalette(styles.build_palette())


def pump(ms=50):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def make_window(name, n=200):
    root = Path(helpers.ROOT) / name
    cfg = Config(root / "settings.json")
    cfg.set("scan_on_start", False)
    cfg.set("music_dirs", [])
    db = Database(root / "lib.db")
    db.upsert_many([row(i, location=f"/nope/{i}.mp3") for i in range(n)])
    engine = AudioEngine()
    eq = Equalizer(cfg)
    window = MainWindow(cfg, db, engine, eq)
    window.show()
    pump(100)
    return window, cfg, db, engine, eq


class GuiTests(unittest.TestCase):
    def test_window_lists_filters_and_switches_views(self):
        translator.set_language("en")
        window, cfg, db, engine, eq = make_window("gui1")
        model = window.table.track_model
        self.assertEqual(model.rowCount(), 200)
        self.assertEqual(window.subtitle_label.text().split(" ")[0], "200")
        window.search.setText("song 19")
        pump(400)
        self.assertEqual(model.rowCount(), len(db.query_ids(text="song 19")))
        window.search.clear()
        pump(400)
        window.sidebar.select("artist", "Artist 1")
        window._show_view("artist", "Artist 1")
        self.assertEqual(model.rowCount(), 40)
        window._show_view("favorites", None)
        self.assertEqual(model.rowCount(), 0)
        self.assertIn("favorites", window.table.empty_title.lower())
        window.close()

    def test_lazy_model_only_loads_visible_pages(self):
        window, cfg, db, engine, eq = make_window("gui2", n=5000)
        model = window.table.track_model
        self.assertEqual(model.rowCount(), 5000)
        self.assertEqual(len(model._pages), 0 if not window.table.isVisible() else len(model._pages))
        self.assertLessEqual(len(model._pages), 4)  # only what the viewport painted
        model.track_at(4999)
        self.assertLessEqual(len(model._pages), 5)
        for start in range(0, 5000, model.PAGE):
            model.track_at(start)
        self.assertLessEqual(len(model._pages), model.MAX_PAGES)
        window.close()

    def test_queue_play_next_and_add_appear_in_queue_view(self):
        window, cfg, db, engine, eq = make_window("gui3", n=30)
        ids = db.query_ids()
        window.queue.set_context(ids, ids[0])
        window.queue.current = ids[0]
        window._play_next([ids[5]])
        window._add_to_queue([ids[7], ids[8]])
        self.assertEqual(window.queue.upcoming()[:4], [ids[5], ids[7], ids[8], ids[1]])
        window.sidebar.select("queue")
        window._show_view("queue", None)
        self.assertEqual(window.table.track_model.ids()[:5], [ids[0], ids[5], ids[7], ids[8], ids[1]])
        window.close()

    def test_favorites_toggle(self):
        window, cfg, db, engine, eq = make_window("gui4", n=10)
        ids = db.query_ids()[:3]
        window._set_favorite(ids, True)
        self.assertEqual(db.count_favorites(), 3)
        window._show_view("favorites", None)
        self.assertEqual(window.table.track_model.rowCount(), 3)
        window.close()

    def test_language_switch_updates_texts_live(self):
        window, cfg, db, engine, eq = make_window("gui5", n=5)
        translator.set_language("en")
        self.assertEqual(window.search.placeholderText(), tr("search.placeholder"))
        english = window.search.placeholderText()
        translator.set_language("es")
        pump(50)
        self.assertNotEqual(window.search.placeholderText(), english)
        self.assertIn("Buscar", window.search.placeholderText())
        translator.set_language("en")
        window.close()

    def test_equalizer_dialog_presets_and_custom(self):
        translator.set_language("en")
        window, cfg, db, engine, eq = make_window("gui6", n=3)
        window.toggle_equalizer()
        dialog = window._eq_dialog
        pump(50)
        self.assertEqual(len(dialog.band_sliders), 10)
        eq.set_enabled(True)
        eq.load_preset("Rock")
        pump(20)
        self.assertEqual([s.value() / 10 for s in dialog.band_sliders], list(map(float, BUILTIN_PRESETS["Rock"])))
        dialog.band_sliders[0].setValue(-100)  # user drags the 60 Hz band
        self.assertEqual(eq.gains[0], -10.0)
        self.assertIsNone(eq.preset)
        self.assertTrue(eq.save_custom("Mine"))
        self.assertFalse(eq.save_custom("Rock"))  # protected name
        cfg.save()
        reloaded = Equalizer(Config(cfg.path))
        self.assertIn("Mine", reloaded.preset_names())
        self.assertEqual(reloaded.gains[0], -10.0)
        window.close()

    def test_airsonic_folder_tree_mirrors_the_server(self):
        translator.set_language("en")
        root = Path(helpers.ROOT) / "gui7"
        cfg = Config(root / "settings.json")
        cfg.set("scan_on_start", False)
        cfg.set("music_dirs", [])
        db = Database(root / "lib.db")
        A = dict(source_type=SOURCE_AIRSONIC)
        db.upsert_many([row(i, location=str(i), folder=f, **A) for i, f in enumerate(
            ["Rock/Band One/Album A", "Rock/Band One/Album A", "Rock/Band One/Album B", "Rock/Band Two/Album C", "Jazz/Solo"])])
        window = MainWindow(cfg, db, AudioEngine(), Equalizer(cfg))
        window.show()
        pump(100)
        sidebar = window.sidebar
        group = sidebar._items[("airsonic", None)]
        group.setExpanded(True)
        pump(50)
        self.assertEqual([group.child(i).text(0) for i in range(group.childCount())], ["Jazz", "Rock"])
        rock = sidebar._items[("folder", "Rock")]
        self.assertEqual(rock.childCount(), 0)                       # sub-folders are built lazily
        rock.setExpanded(True)
        self.assertEqual([rock.child(i).text(0) for i in range(rock.childCount())], ["Band One", "Band Two"])
        sidebar.select("folder", "Rock/Band One")
        window._show_view("folder", "Rock/Band One")
        self.assertEqual(window.table.track_model.rowCount(), 3)
        self.assertEqual(window.title_label.text(), "Band One")
        self.assertIn("Rock/Band One", window.subtitle_label.text())
        window._show_view("folder", "Rock")
        self.assertEqual(window.table.track_model.rowCount(), 4)
        window.close()

    def test_playlists_from_plus_button_to_delete(self):
        translator.set_language("en")
        window, cfg, db, engine, eq = make_window("gui8", n=12)
        ids = db.query_ids()
        sidebar = window.sidebar
        fired = []
        sidebar.new_playlist_requested.connect(lambda: fired.append(1))
        names = iter([None, "Fiesta", "Fiesta"])           # first prompt is cancelled by the "user"
        original = (main_window_module.ask_text, main_window_module.confirm)
        main_window_module.ask_text = lambda *a, **k: next(names)
        main_window_module.confirm = lambda *a, **k: True
        try:
            box = sidebar._plus_rect()
            self.assertEqual((box.width(), box.height()), (26, 26))
            QTest.mouseClick(sidebar.viewport(), Qt.LeftButton, pos=box.center())  # the visible "+"
            self.assertEqual(fired, [1])
            self.assertEqual(db.playlists(), [])                                  # cancelled: nothing created
            window._new_playlist([ids[0], ids[1]])
            pid = window._view[1]
            self.assertEqual(window._view[0], "playlist")
            self.assertEqual(window.title_label.text(), "Fiesta")
            self.assertEqual(window.table.track_model.rowCount(), 2)
            window._add_to_playlist(pid, [ids[2]])
            self.assertEqual(window.table.track_model.rowCount(), 3)
            self.assertEqual(sidebar._items[("playlist", pid)].data(0, COUNT_ROLE), 3)
            window._remove_from_playlist([ids[0]])
            self.assertEqual(window.table.track_model.ids(), [ids[1], ids[2]])
            window._new_playlist()                                                   # same name again -> made unique
            self.assertEqual(sorted(n for _, n, _c in db.playlists()), ["Fiesta", "Fiesta (2)"])
            self.assertEqual(window.table.playlists[0][1], "Fiesta")                 # offered in "Add to playlist"
            window._delete_playlist(window._view[1])
            self.assertEqual(window._view, ("all", None))
            self.assertEqual([n for _, n, _c in db.playlists()], ["Fiesta"])
        finally:
            main_window_module.ask_text, main_window_module.confirm = original
            window.close()

    def test_empty_states_offer_a_button_and_settings_is_always_visible(self):
        translator.set_language("en")
        window, cfg, db, engine, eq = make_window("gui9", n=0)
        self.assertTrue(window.settings_button.isVisible())
        self.assertEqual(window.settings_button.text().strip("\u2002"), tr("sidebar.settings"))
        table = window.table
        self.assertTrue(table.empty_button.isVisible())
        self.assertEqual(table.empty_button.text(), tr("empty.library.action"))
        opened = []
        window.open_settings = lambda tab=0: opened.append(tab)
        table.empty_button.click()
        self.assertEqual(opened, [1])                                                # straight to the Library tab
        window._show_view("airsonic", None)
        self.assertEqual(table.empty_button.text(), tr("empty.airsonic.action"))
        table.empty_button.click()
        self.assertEqual(opened, [1, 2])                                             # straight to the Airsonic tab
        window.close()

    def test_icons_are_vector_and_hidpi_sharp(self):
        small, big = icons.render_svg(icons._svg("play", "#ffffff"), 24, 1.0), icons.render_svg(icons._svg("play", "#ffffff"), 24, 2.0)
        self.assertEqual((small.width(), big.width()), (24, 48))
        self.assertEqual(big.devicePixelRatio(), 2.0)
        for name in icons._GLYPHS:
            self.assertFalse(icons.glyph(name, "#ffffff", 20).isNull(), name)


class LightweightTests(unittest.TestCase):
    """Guard the low-memory / low-battery behaviour."""

    def test_heavy_libraries_are_not_imported_at_start_up(self):
        import subprocess
        import sys as _sys
        code = ("import sys; import juke.gui.main_window, juke.audio.engine, juke.api.airsonic, juke.db.indexer; "
                "bad = [m for m in ('httpx', 'mutagen', 'vlc', 'yt_dlp', 'anyio') if m in sys.modules]; "
                "print('LOADED:' + ','.join(bad))")
        env = dict(__import__("os").environ, QT_QPA_PLATFORM="offscreen")
        out = subprocess.run([_sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "LOADED:", out.stderr[-400:])

    def test_idle_engine_has_no_timer_and_has_not_loaded_libvlc(self):
        engine = AudioEngine()
        self.assertFalse(engine._backend_tried)
        self.assertIsNone(engine._player)
        self.assertFalse(engine._timer.isActive())            # an idle Juke never wakes the CPU
        engine.set_volume(30)                                  # settings before the first Play are just remembered
        engine.set_muted(True)
        engine.set_rate(1.25)
        self.assertFalse(engine._backend_tried)
        self.assertEqual((engine.volume, engine.muted, engine.rate), (30, True, 1.25))

    def test_level_meter_is_still_unless_allowed_and_visible(self):
        from juke.gui.components.top_bar import SpectrumWidget
        meter = SpectrumWidget()
        meter.show()
        meter.set_active(True)
        self.assertTrue(meter._timer.isActive())               # playing, in front, allowed: animates
        meter.set_animation_allowed(False)
        for _ in range(60):
            meter._tick()
        self.assertFalse(meter._timer.isActive())              # on battery / window hidden: a still picture
        meter.set_animation_allowed(True)
        self.assertTrue(meter._timer.isActive())
        meter.set_active(False)
        for _ in range(80):
            meter._tick()
        self.assertFalse(meter._timer.isActive())              # stopped: fully at rest
        meter.hide()
        meter.set_active(True)
        self.assertFalse(meter._timer.isActive())              # hidden windows never animate

    def test_battery_detection_from_sysfs(self):
        import tempfile
        from pathlib import Path as P
        import juke.power as power

        def supply(root, name, **files):
            d = P(root) / name
            d.mkdir()
            for k, v in files.items():
                (d / k).write_text(v + "\n")

        original = power._SUPPLIES
        try:
            with tempfile.TemporaryDirectory() as root:
                supply(root, "BAT0", type="Battery", status="Discharging")
                supply(root, "ADP1", type="Mains", online="0")
                supply(root, "mouse", type="Battery", status="Discharging", scope="Device")
                power._SUPPLIES = P(root)
                self.assertTrue(power.on_battery())
                (P(root) / "ADP1" / "online").write_text("1\n")           # charger plugged in
                self.assertFalse(power.on_battery())
            with tempfile.TemporaryDirectory() as root:                    # desktop: no battery at all
                supply(root, "AC", type="Mains", online="1")
                power._SUPPLIES = P(root)
                self.assertFalse(power.on_battery())
            power._SUPPLIES = P("/nonexistent/power_supply")
            self.assertFalse(power.on_battery())
        finally:
            power._SUPPLIES = original

    def test_window_freezes_meter_and_slows_polling_when_hidden_or_on_battery(self):
        import juke.gui.main_window as mw
        window, cfg, db, engine, eq = make_window("gui10", n=3)
        original = mw.on_battery
        try:
            mw.on_battery = lambda: True
            cfg.set("meter", "auto")
            self.assertFalse(window._meter_allowed())          # battery + auto -> still
            cfg.set("meter", "on")
            self.assertTrue(window._meter_allowed())           # the user can insist
            cfg.set("meter", "off")
            mw.on_battery = lambda: False
            self.assertFalse(window._meter_allowed())
            cfg.set("meter", "auto")
            self.assertTrue(window._meter_allowed())           # mains power
            window.hide()
            self.assertFalse(engine._ui_active)                # hidden: engine polls lazily
            self.assertEqual(engine._timer.interval(), 2000)
            window.show()
            pump(50)
        finally:
            mw.on_battery = original
            window.close()


@unittest.skipUnless(AudioEngine().available, "libVLC not available")
class PlaybackTests(unittest.TestCase):
    def test_local_file_plays_seeks_and_finishes_with_eq_applied(self):
        translator.set_language("en")
        root = Path(helpers.ROOT) / "play"
        root.mkdir()
        wav = root / "tone.wav"
        write_wav(wav, 2.5, rate=22050)
        cfg = Config(root / "settings.json")
        cfg.set("volume", 8)
        engine = AudioEngine()
        engine.set_volume(8)
        eq = Equalizer(cfg)
        eq.set_enabled(True)
        eq.load_preset("Bass Boost")
        engine.attach_equalizer(eq)
        self.assertIsNone(engine._vlc_eq)                    # libVLC is not even loaded before the first Play
        states, finished = [], []
        engine.state_changed.connect(states.append)
        engine.track_finished.connect(lambda: finished.append(True))
        self.assertTrue(engine.play_url(wav.resolve().as_uri()))
        player_before = engine._player
        self.assertIsNotNone(engine._vlc_eq)                 # ...and the equalizer is applied by it
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and engine.position_ms() < 400:
            pump(50)
        self.assertGreaterEqual(engine.position_ms(), 300, "playback did not advance")
        self.assertIn("playing", states)
        engine.set_rate(1.5)
        self.assertAlmostEqual(engine._player.get_rate(), 1.5, places=1)
        engine.seek(0.5)
        pump(300)
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and not finished:
            pump(50)
        self.assertTrue(finished, "track_finished was not emitted")
        # second track on the SAME player: pipeline object and equalizer survive
        self.assertTrue(engine.play_url(wav.resolve().as_uri()))
        self.assertIs(engine._player, player_before)
        self.assertIsNotNone(engine._vlc_eq)
        pump(300)
        eq.set_enabled(False)
        self.assertIsNone(engine._vlc_eq)
        engine.stop()
        engine.shutdown()


if __name__ == "__main__":
    unittest.main()
