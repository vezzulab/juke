"""Offscreen smoke tests of the real widgets, plus playback through libVLC when available."""

import time
import unittest
from pathlib import Path

from . import helpers

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

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
            box = sidebar._plus_rect("lists")
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

    def test_empty_states_offer_a_button_and_the_sidebar_footer_only_has_support(self):
        translator.set_language("en")
        window, cfg, db, engine, eq = make_window("gui9", n=0)
        self.assertFalse(hasattr(window, "settings_button"))              # Settings lives only in the ⋯ menu
        self.assertEqual(window.support_button.text().strip("\u2002"), tr("sidebar.support"))
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


class ThemeTests(unittest.TestCase):
    def tearDown(self):
        styles.set_theme("dark")

    @staticmethod
    def _luminance(hex_color):
        channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def contrast(self, a, b):
        high, low = sorted((self._luminance(a), self._luminance(b)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    def test_both_palettes_are_legible(self):
        """WCAG: 7:1 for body text, 4.5:1 for secondary text and text on the accent, 3:1 for UI glyphs."""
        needs = [("TEXT", "BASE", 7), ("TEXT", "PANEL", 7), ("TEXT", "ALT_ROW", 7), ("SUBTEXT", "BASE", 4.5),
                 ("SUBTEXT", "MANTLE", 4.5), ("SUBTEXT", "PANEL", 4.5), ("MUTED", "BASE", 3), ("ACCENT", "BASE", 3),
                 ("ACCENT", "MANTLE", 3), ("ON_ACCENT", "ACCENT", 4.5), ("ON_ACCENT", "ACCENT2", 4.5),
                 ("ON_ACCENT", "ACCENT_HOVER", 4.5), ("ON_ACCENT", "ACCENT2_HOVER", 4.5), ("RED", "BASE", 3), ("GREEN", "BASE", 3)]
        for name, table in styles.THEMES.items():
            for fg, bg, minimum in needs:
                self.assertGreaterEqual(self.contrast(table[fg], table[bg]), minimum, f"{name}: {fg} on {bg}")

    def test_switching_changes_stylesheet_palette_and_helpers(self):
        from juke.gui.theme import ThemeManager, resolve
        self.assertEqual((resolve("dark"), resolve("light")), ("dark", "light"))
        self.assertEqual(resolve("auto"), "dark")                     # offscreen reports no scheme: default to Juke's own look
        manager = ThemeManager(app, "light")
        self.assertEqual(manager.apply(), "light")
        self.assertTrue(styles.NAME == "light" and not styles.is_dark())
        self.assertEqual(styles.BASE, styles.LIGHT["BASE"])
        css = app.styleSheet()
        self.assertIn(styles.LIGHT["BASE"], css)
        self.assertNotIn(styles.DARK["BASE"], css)
        self.assertEqual(app.palette().window().color().name(), styles.LIGHT["BASE"])
        manager.apply("dark")
        self.assertEqual(styles.BASE, styles.DARK["BASE"])
        self.assertIn(styles.DARK["BASE"], app.styleSheet())

    def test_every_widget_rebuilds_its_colours(self):
        translator.set_language("en")
        window, cfg, db, engine, eq = make_window("gui-theme", n=6)
        stop = window.top_bar.btn_stop

        def icon_ink():                                               # colour of the solid centre of the "stop" square
            return stop.icon().pixmap(24, 24).toImage().pixelColor(12, 12).name()

        window.theme.apply("dark")
        self.assertEqual(icon_ink(), styles.DARK["TEXT"])
        window.theme.apply("light")
        self.assertEqual(icon_ink(), styles.LIGHT["TEXT"])            # top-bar icons follow
        self.assertEqual(window.table.track_model._accent.name(), styles.LIGHT["ACCENT"])
        sidebar_icon = window.sidebar._items[("all", None)].icon(0).pixmap(18, 18, mode=__import__("PySide6.QtGui", fromlist=["QIcon"]).QIcon.Normal,
                                                                         state=__import__("PySide6.QtGui", fromlist=["QIcon"]).QIcon.Off)
        self.assertFalse(sidebar_icon.isNull())
        cover = window.top_bar.lcd.cover.pixmap().toImage()
        self.assertGreater(sum(cover.pixelColor(cover.width() // 2, y).lightness() for y in range(4, 12)) / 8, 150)   # light placeholder
        window.toggle_theme()                                          # menu action / Ctrl+T
        self.assertEqual(styles.NAME, "dark")
        self.assertEqual(cfg.get("theme"), "dark")
        window.close()
        window.theme.apply("dark")


class IcyTitleTests(unittest.TestCase):
    """libVLC does not request ICY titles on https:// streams, so Juke reads them itself."""

    def run_async(self, coro):
        import asyncio
        return asyncio.run(coro)

    def test_reads_the_first_metadata_block_and_filters_placeholders(self):
        import asyncio
        from juke.audio.icy import clean_stream_title, parse_metadata_block, read_stream_title

        block = lambda text: text.encode() + b"\0" * (-len(text.encode()) % 16)
        self.assertEqual(parse_metadata_block(b"StreamTitle='Marc Anthony - Vivir Mi Vida';StreamUrl='x';\0\0"), "Marc Anthony - Vivir Mi Vida")
        self.assertEqual(parse_metadata_block("StreamTitle='Niño Corazón';".encode("latin-1")), "Niño Corazón")   # not valid UTF-8
        self.assertEqual(parse_metadata_block(b"StreamUrl='x';"), "")
        self.assertEqual(clean_stream_title("Now Playing info goes here", "Fuego"), "")
        self.assertEqual(clean_stream_title("  Fuego  ", "Fuego"), "")                                       # just the station name
        self.assertEqual(clean_stream_title(" - "), "")
        self.assertEqual(clean_stream_title("Electric  Skychurch - Heaven"), "Electric Skychurch - Heaven")

        async def serve_and_read(metadata, metaint=1000, status=b"ICY 200 OK"):
            async def serve(reader, writer):
                request = await reader.readuntil(b"\r\n\r\n")
                assert b"Icy-MetaData: 1" in request
                writer.write(status + b"\r\nicy-name: X\r\n" + (f"icy-metaint: {metaint}\r\n".encode() if metaint else b"") + b"\r\n")
                writer.write(b"\xff\xfb" * (metaint // 2))
                data = block(metadata)
                writer.write(bytes([len(data) // 16]) + data)
                await writer.drain()
                writer.close()

            server = await asyncio.start_server(serve, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            try:
                return await read_stream_title(f"http://127.0.0.1:{port}/stream", timeout=5)
            finally:
                server.close()
                await server.wait_closed()

        self.assertEqual(self.run_async(serve_and_read("StreamTitle='Gilberto Santa Rosa - Que Alguien Me Diga';")), "Gilberto Santa Rosa - Que Alguien Me Diga")
        self.assertEqual(self.run_async(serve_and_read("StreamTitle='A - B';", status=b"HTTP/1.0 200 OK")), "A - B")     # both dialects
        self.assertEqual(self.run_async(serve_and_read("")), "")                                                       # empty first block
        self.assertEqual(self.run_async(serve_and_read("StreamTitle='x';", metaint=0)), "")                            # server sends no metadata
        self.assertEqual(self.run_async(read_stream_title("http://127.0.0.1:1/none", timeout=2)), "")                  # nothing listens: no exception
        self.assertEqual(self.run_async(read_stream_title("ftp://x.example/a")), "")

    def test_engine_keeps_looking_while_live_and_announces_changes(self):
        import juke.audio.engine as engine_module
        import juke.audio.icy as icy_module
        answers = iter(["Now Playing info goes here", "Artist - First Song", "Artist - First Song", "Artist - Second Song"])
        looked = []

        async def fake(url, timeout=10.0):
            looked.append(url)
            return next(answers, "Artist - Second Song")

        original = icy_module.read_stream_title, engine_module.ICY_EVERY_MS
        icy_module.read_stream_title, engine_module.ICY_EVERY_MS = fake, 40
        engine = AudioEngine()
        heard = []
        engine.now_playing_changed.connect(heard.append)
        try:
            engine._live, engine._state, engine._ui_active = True, "playing", True
            engine._station_name, engine._url, engine._icy_token = "Cima", "https://s.example:8146/stream", 7
            engine._lookup_title(7)
            end = time.monotonic() + 8
            while time.monotonic() < end and len(heard) < 2:
                pump(20)
            self.assertEqual(heard, ["Artist - First Song", "Artist - Second Song"])   # placeholder skipped, repeat not re-announced
            self.assertGreaterEqual(len(looked), 4)
            self.assertEqual(engine.now_playing(), "Artist - Second Song")
            count = len(looked)
            engine._ui_active = False                                                       # window hidden: no more requests
            pump(300)
            self.assertLessEqual(len(looked) - count, 1)
            engine._live = False                                                            # station left: the chain ends
            pump(300)
            settled = len(looked)
            pump(300)
            self.assertEqual(len(looked), settled)
            engine._icy_token += 1                                                          # a lookup for a previous station is ignored
            engine._live, engine._ui_active = True, True
            engine._lookup_title(7)
            pump(200)
            self.assertEqual(len(looked), settled)
        finally:
            icy_module.read_stream_title, engine_module.ICY_EVERY_MS = original


class RadioFlowTests(unittest.TestCase):
    def setUp(self):
        translator.set_language("en")
        self.window, self.cfg, self.db, self.engine, self.eq = make_window(f"gui-radio-{self._testMethodName}", n=2)   # own database per test
        import juke.api.radio as radio_api
        self.radio_api = radio_api
        self.played = []
        self.engine.play_url = lambda url: (self.played.append(url), True)[1]       # no audio device needed here
        self._refresh = radio_api.refresh_station

    def tearDown(self):
        self.radio_api.refresh_station = self._refresh
        self.window.close()

    def cima(self, **kw):
        base = dict(id=0, name="Cima 100.5", stream_url="https://s.example:8146/stream", tags="latino, pop", country="Dominican Republic",
                    codec="AAC", bitrate=128, uuid="u-1", source_url="https://cima.example/")
        base.update(kw)
        from juke.db.database import Station
        return Station(**base)

    def spin_until(self, condition, seconds=5):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not condition():
            pump(20)
        return condition()

    def test_radio_section_in_the_sidebar_starts_empty_and_switches_the_view(self):
        w = self.window
        self.assertEqual(w.sidebar._headers["radio"].text(0), "RADIO")
        self.assertEqual(w.sidebar._items[("stations", None)].text(0), "My Stations")
        self.assertEqual(w.sidebar._items[("explore", None)].text(0), "Explore Radio")
        self.assertEqual(self.db.count_stations(), 0)                                  # nothing is preinstalled
        w.sidebar.select("stations")
        w._show_view("stations", None)
        self.assertIs(w.stack.currentWidget(), w.radio_view)
        self.assertTrue(w.add_station_button.isVisible())
        self.assertEqual(w.title_label.text(), "My Stations")
        self.assertEqual(w.radio_view._message.title.text(), "No stations saved yet")
        w._show_view("all", None)
        self.assertIs(w.stack.currentWidget(), w.table)
        self.assertFalse(w.add_station_button.isVisible())
        translator.set_language("es")
        pump(50)
        self.assertEqual(w.sidebar._items[("stations", None)].text(0), "Mis Emisoras")
        self.assertEqual(w.add_station_button.text(), "Añadir emisora por URL…")
        translator.set_language("en")

    def test_save_list_filter_and_remove(self):
        w = self.window
        w._show_view("stations", None)
        w._save_station(self.cima())
        w._save_station(self.cima(name="Fuego", stream_url="https://r.example/8390/stream", uuid="u-2", source_url="", tags="rock", country="DR"))
        self.assertEqual(self.db.count_stations(), 2)
        self.assertEqual(w.sidebar._items[("stations", None)].data(0, COUNT_ROLE), 2)
        self.assertEqual([r.station.name for r in w.radio_view._rows], ["Cima 100.5", "Fuego"])
        self.assertEqual(w.subtitle_label.text(), "2 stations")
        w.radio_view.set_filter_text("fuego rock")
        self.assertEqual([r.station.name for r in w.radio_view._rows], ["Fuego"])
        w.radio_view.set_filter_text("zzz")
        self.assertEqual(w.radio_view._message.title.text(), "No stations found")
        w.radio_view.set_filter_text("")
        gone = w.radio_view._rows[0].station
        w._remove_station(gone)
        self.assertEqual(self.db.count_stations(), 1)
        self.assertEqual(w.subtitle_label.text(), "1 station")

    def test_explore_uses_the_directory_and_marks_saved_ones(self):
        import juke.gui.components.radio_view as rv
        queries = []

        class FakeClient:
            async def search(self, name="", tag="", limit=60):
                queries.append((name, tag))
                if name == "boom":
                    raise self_module.RadioBrowserError("no server answered")
                return [self_module.Station(0, "Latina Salsa", "http://a.example/x.mp3", tags="latin", country="France", codec="MP3", bitrate=128),
                        self_module.Station(0, "Cima 100.5", "https://s.example:8146/stream", country="DR", codec="AAC", bitrate=128)]

            async def aclose(self):
                pass

        from juke.db import database as self_module_db
        self_module = type("M", (), {"Station": self_module_db.Station, "RadioBrowserError": self.radio_api.RadioBrowserError})
        original = rv.radio.RadioBrowserClient
        rv.radio.RadioBrowserClient = FakeClient
        try:
            w = self.window
            self.db.add_station(self.cima())                                             # already saved
            w.sidebar.select("explore")
            w._show_view("explore", None)
            self.assertTrue(self.spin_until(lambda: len(w.radio_view._rows) == 2))
            self.assertEqual(queries[-1], ("", ""))
            self.assertTrue(w.radio_view._chips.isVisible())
            saved_flags = {r.station.name: not r.action_button.isEnabled() for r in w.radio_view._rows}
            self.assertEqual(saved_flags, {"Latina Salsa": False, "Cima 100.5": True})   # the saved one cannot be saved twice
            w.radio_view._chip_buttons[1].click()                                        # the first genre chip (index 0 is "All")
            self.assertTrue(self.spin_until(lambda: queries[-1] == ("", rv.CHIPS[0])))
            w.search.setText("boom")                                                     # typed search hits the directory (debounced)
            self.assertTrue(self.spin_until(lambda: queries[-1][0] == "boom" and w.radio_view._message.button.isVisible()))
            self.assertEqual(w.radio_view._message.title.text(), "Could not reach the radio directory")
            w.radio_view._rows.clear()
        finally:
            rv.radio.RadioBrowserClient = original

    def test_add_by_url_dialog_shows_progress_then_the_found_signal(self):
        from juke.api.radio_resolver import ResolveError
        from juke.gui.radio_dialog import AddStationDialog
        gate = {"release": False}

        async def slow(url):
            import asyncio
            while not gate["release"]:
                await asyncio.sleep(0.01)
            if "nothing" in url:
                raise ResolveError("no_audio")
            return {"stream_url": "https://s.example:8146/stream", "title": "Radio Cima", "favicon": "", "tags": "latino",
                    "codec": "AAC", "bitrate": 128, "homepage": "https://cima.example/", "source": "page", "live": True}

        dialog = AddStationDialog(self.window, resolver=slow)
        dialog.show()
        dialog.url.setText("cima.example/player")
        dialog.find_button.click()
        pump(60)
        self.assertTrue(dialog.progress.isVisible())
        self.assertEqual(dialog.status.text(), "Searching for an audio signal…")            # the loading indicator asked for
        self.assertFalse(dialog.url.isEnabled())
        self.assertFalse(dialog.add_button.isEnabled())
        gate["release"] = True
        self.assertTrue(self.spin_until(lambda: dialog.found_panel.isVisible()))
        self.assertFalse(dialog.progress.isVisible())
        self.assertEqual(dialog.name.text(), "Radio Cima")
        self.assertTrue(dialog.add_button.isEnabled())
        dialog.name.setText("Cima FM")
        station = dialog.station()
        self.assertEqual((station.name, station.stream_url, station.bitrate), ("Cima FM", "https://s.example:8146/stream", 128))
        self.assertEqual(station.source_url, "https://cima.example/player")                 # remembered: streams move, pages do not
        dialog.url.setText("https://nothing.example/")                                       # a failing search
        dialog.find_button.click()
        self.assertTrue(self.spin_until(lambda: "No audio signal" in dialog.status.text()))
        self.assertIn("Explore Radio", dialog.status.text())                                # points news sites to the directory
        self.assertTrue(dialog.url.isEnabled())
        dialog.reject()

    def test_live_display_now_playing_and_leaving_the_station(self):
        from juke.audio.engine import AudioEngine
        w = self.window
        station = self.cima()
        w._play_station(station, refresh=False)
        lcd = w.top_bar.lcd
        self.assertEqual(self.played, ["https://s.example:8146/stream"])
        self.assertTrue(lcd.live_badge.isVisible())                                          # the LIVE icon
        self.assertEqual(lcd.title.text(), "Cima 100.5")                                     # the station's name
        self.assertEqual(lcd.progress_stack.currentIndex(), 1)                               # no seek bar for a live stream
        self.assertEqual(lcd.subtitle.text(), "Connecting…")
        self.assertIn("AAC 128 kbps", lcd.live_info.text())
        self.engine.now_playing_changed.emit("Marc Anthony - Vivir Mi Vida")                 # what the ICY metadata reports
        self.assertEqual(lcd.subtitle.text(), "Marc Anthony - Vivir Mi Vida")
        self.assertEqual(w.windowTitle(), "Marc Anthony - Vivir Mi Vida — Cima 100.5 · Juke")
        self.engine.now_playing_changed.emit("")                                             # between songs: back to the station info
        self.assertIn("AAC 128", lcd.subtitle.text())
        self.assertTrue(self.engine._live)
        ids = self.db.query_ids()
        w.queue.set_context(ids, ids[0])
        w.resolver.resolve = lambda track: "file:///music/song.mp3"                          # the fake library has no real files
        w._start(ids[0])                                                                     # play a song: radio state is dropped
        self.assertFalse(lcd.live_badge.isVisible())
        self.assertIsNone(w.current_station)
        self.assertFalse(self.engine._live)
        self.assertEqual(lcd.progress_stack.currentIndex(), 0)

    def test_a_dead_or_moved_stream_is_replaced_by_the_station_current_address(self):
        w = self.window
        saved_id = self.db.add_station(self.cima())
        old = self.cima(id=saved_id)
        fresh = self.cima(id=saved_id, stream_url="https://new.example:9000/live", bitrate=64)
        asked = []

        async def refresh(station, **kw):
            asked.append(station.stream_url)
            return fresh

        self.radio_api.refresh_station = refresh
        w._play_station(old)                                                                 # plays the saved address at once...
        self.assertEqual(self.played[0], "https://s.example:8146/stream")
        self.assertTrue(self.spin_until(lambda: len(self.played) == 2))                     # ...then follows the moved station
        self.assertEqual(self.played[1], "https://new.example:9000/live")
        self.assertEqual(self.db.stations()[0].stream_url, "https://new.example:9000/live")   # and remembers it
        self.assertEqual(w.current_station.stream_url, "https://new.example:9000/live")
        self.assertEqual(asked, ["https://s.example:8146/stream"])
        # the stream dies: one new lookup, then give up cleanly if there is nothing new
        results = [None]

        async def nothing(station, **kw):
            return results[0]

        self.radio_api.refresh_station = nothing
        w._station_failed()
        self.assertTrue(self.spin_until(lambda: w.current_station is None))
        self.assertFalse(w.top_bar.lcd.live_badge.isVisible())
        self.assertEqual(w.windowTitle(), "Juke")

    def test_station_on_the_air_offers_stop_instead_of_play(self):
        w = self.window
        w._save_station(self.cima())
        w._save_station(self.cima(name="Fuego", stream_url="https://r.example/8390/stream", uuid="u-2", source_url=""))
        w.sidebar.select("stations")
        w._show_view("stations", None)
        first, second = w.radio_view._rows
        self.assertEqual(first.play_button.toolTip(), "Listen")
        w._play_station(first.station, refresh=False)
        self.engine._set_state("playing")                                                    # the fake sink never reports it
        pump(30)
        self.assertEqual((first.play_button.toolTip(), second.play_button.toolTip()), ("Stop", "Listen"))
        first.play_button.click()                                                            # the same button now stops
        pump(30)
        self.assertEqual(self.engine.state, "stopped")
        self.assertEqual(first.play_button.toolTip(), "Listen")
        self.played.clear()
        first.play_button.click()                                                            # and plays again
        self.assertEqual(self.played, ["https://s.example:8146/stream"])
        self.engine._set_state("paused")
        pump(30)
        self.assertEqual(first.play_button.toolTip(), "Listen")                                # paused: offers to resume
        self.engine._set_state("playing")
        w._play_station(second.station, refresh=False)                                       # another station takes over
        pump(30)
        self.assertEqual((first.play_button.toolTip(), second.play_button.toolTip()), ("Listen", "Stop"))
        translator.set_language("es")
        pump(50)
        self.assertEqual(second.play_button.toolTip(), "Detener")

    def test_add_by_url_offers_every_station_the_page_lists(self):
        from juke.gui.radio_dialog import AddStationDialog

        async def many(url):
            return [{"stream_url": f"https://r.example/{n}/;", "title": f"Radio {n}", "favicon": "", "tags": "",
                     "codec": "MP3", "bitrate": 128, "homepage": "", "source": "page", "live": True} for n in (1, 2, 3)]

        dialog = AddStationDialog(self.window, resolver=many)
        dialog.show()
        dialog.url.setText("https://portal.example/")
        dialog.find_button.click()
        self.assertTrue(self.spin_until(lambda: dialog.many_panel.isVisible()))
        self.assertFalse(dialog.found_panel.isVisible())
        self.assertEqual(dialog.many_list.count(), 3)
        self.assertEqual(dialog.add_button.text(), "Add 3 stations")
        dialog.many_list.item(1).setCheckState(Qt.Unchecked)
        self.assertEqual(dialog.add_button.text(), "Add 2 stations")
        chosen = dialog.stations()
        self.assertEqual([s.name for s in chosen], ["Radio 1", "Radio 3"])
        self.assertTrue(all(s.source_url == "https://portal.example/" for s in chosen))     # each can be re-found on the page
        for i in (0, 2):
            dialog.many_list.item(i).setCheckState(Qt.Unchecked)
        self.assertFalse(dialog.add_button.isEnabled())
        dialog.reject()

    def test_saving_several_stations_at_once(self):
        w = self.window
        for n in (1, 2, 3):
            w._save_station(self.cima(name=f"Radio {n}", stream_url=f"https://r.example/{n}/;", uuid="", source_url="https://portal.example/"),
                            quiet=True)
        self.assertEqual(self.db.count_stations(), 3)

    def test_stopped_station_is_tuned_in_again_by_play(self):
        w = self.window
        w._play_station(self.cima(uuid="", source_url=""))
        w._stop()
        self.played.clear()
        w._play_pressed()
        self.assertEqual(self.played, ["https://s.example:8146/stream"])


class UpdateFlowTests(unittest.TestCase):
    def setUp(self):
        translator.set_language("en")
        self.window, self.cfg, self.db, self.engine, self.eq = make_window(f"gui-update-{self._testMethodName}", n=2)
        import juke.gui.main_window as mw
        self.mw = mw
        from juke.updater import ReleaseInfo
        self.newer = ReleaseInfo("v9.0.0", "9.0.0", "## Big\n- things", "https://github.com/vezzulab/juke/releases/tag/v9.0.0",
                                 "https://dl.example/x", 10, "")
        self.asked, self.notices, self.opened = [], [], []
        self.window._ask_update = lambda release: (self.asked.append(release.version), self.answer)[1]
        self._notice, self._open = mw.notice, mw.QDesktopServices.openUrl
        mw.notice = lambda parent, title, text: self.notices.append(text)
        mw.QDesktopServices.openUrl = staticmethod(lambda url: self.opened.append(url.toString()) or True)
        self.answer = "later"

    def tearDown(self):
        self.mw.notice, self.mw.QDesktopServices.openUrl = self._notice, self._open
        self.window.close()

    def test_dialog_lets_the_user_decide(self):
        from juke.gui.update_dialog import UpdateDialog
        dialog = UpdateDialog(self.newer, "0.1.0", True)                             # two answers: Update or Cancel
        self.assertEqual({b.text() for b in dialog.findChildren(QPushButton)}, {tr("update.accept"), tr("dialog.cancel")})
        dialog.cancel_button.click()
        self.assertEqual(dialog.choice, "later")
        dialog = UpdateDialog(self.newer, "0.1.0", True)
        dialog.dont_ask.setChecked(True)                                             # ...and Cancel can mean "not this version"
        dialog.cancel_button.click()
        self.assertEqual(dialog.choice, "skip")
        dialog = UpdateDialog(self.newer, "0.1.0", True)
        dialog.reject()                                                              # Esc is a Cancel too
        self.assertEqual(dialog.choice, "later")
        dialog = UpdateDialog(self.newer, "0.1.0", True)
        dialog.primary_button.click()
        self.assertEqual(dialog.choice, "update")
        manual = UpdateDialog(self.newer, "0.1.0", False)                            # source install: cannot self-update
        self.assertEqual(manual.primary_button.text(), tr("update.open_page"))
        manual.primary_button.click()
        self.assertEqual(manual.choice, "page")
        shown = UpdateDialog(self.newer, "0.1.0", True)
        self.assertIn("things", shown.notes.toPlainText())                           # release notes are rendered
        from PySide6.QtWidgets import QLabel
        texts = [label.text() for label in shown.findChildren(QLabel)]
        self.assertTrue(any("9.0.0" in t for t in texts) and any("0.1.0" in t for t in texts))
        self.assertTrue(any("Update to Juke 9.0.0?" in t for t in texts))            # the question names the version

    def test_skipped_version_stays_quiet_until_asked_manually(self):
        self.answer = "skip"
        self.window._update_checked(self.newer, manual=False)
        self.assertEqual(self.asked, ["9.0.0"])
        self.assertEqual(self.cfg.get("update.skipped"), "9.0.0")
        self.window._update_checked(self.newer, manual=False)                        # next automatic check: silent
        self.assertEqual(self.asked, ["9.0.0"])
        self.answer = "later"
        self.window._update_checked(self.newer, manual=True)                         # "Check for updates…": asks again
        self.assertEqual(self.asked, ["9.0.0", "9.0.0"])

    def test_up_to_date_is_silent_unless_you_asked(self):
        from juke.updater import ReleaseInfo
        same = ReleaseInfo("v0.1.0", "0.1.0", "", "", "", 0, "")
        self.window._update_checked(same, manual=False)
        self.window._update_checked(None, manual=False)
        self.assertEqual((self.asked, self.notices), ([], []))
        self.window._update_checked(same, manual=True)
        self.assertEqual(len(self.notices), 1)
        self.assertIn("up to date", self.notices[0])
        self.assertEqual(self.asked, [])

    def test_page_choice_and_no_self_update_open_the_release_page(self):
        self.answer = "page"
        self.window._update_checked(self.newer, manual=True)
        self.assertEqual(self.opened, [self.newer.page_url])
        self.answer = "update"                                                       # not an AppImage here -> download page
        self.window._update_checked(self.newer, manual=True)
        self.assertEqual(self.opened, [self.newer.page_url] * 2)

    def test_every_start_checks_and_it_can_be_switched_off(self):
        """Regression: a once-a-day limit hid a release published an hour after the last check."""
        import time as _time
        calls = []
        self.window.check_for_updates = lambda manual=False: calls.append(manual)
        self.cfg.set("update.enabled", True)
        self.cfg.set("update.last_check", _time.time())                              # checked a minute ago...
        self.window._auto_update_check()
        self.assertEqual(calls, [False])                                             # ...and it asks again anyway
        self.assertTrue(self.window._recheck_timer.isActive())                       # then again every 30 minutes while open
        self.assertEqual(self.window._recheck_timer.interval(), 30 * 60 * 1000)
        self.cfg.set("update.enabled", False)
        self.window._auto_update_check()
        self.assertEqual(calls, [False])                                             # switched off: never asks GitHub

    def test_later_snoozes_only_that_version_for_a_day(self):
        import time as _time
        self.answer = "later"
        self.window._update_checked(self.newer, manual=False)
        self.assertEqual(self.asked, ["9.0.0"])
        self.assertEqual(self.cfg.get("update.snoozed"), "9.0.0")
        self.assertGreater(self.cfg.get("update.snooze_until"), _time.time() + 23 * 3600)
        self.window._update_checked(self.newer, manual=False)                        # next automatic check: quiet
        self.assertEqual(self.asked, ["9.0.0"])
        from juke.updater import ReleaseInfo
        newest = ReleaseInfo("v9.1.0", "9.1.0", "", "", "", 0, "")
        self.window._update_checked(newest, manual=False)                            # a newer version is news again
        self.assertEqual(self.asked, ["9.0.0", "9.1.0"])
        self.window._update_checked(self.newer, manual=True)                         # "Check for updates…" always asks
        self.assertEqual(self.asked, ["9.0.0", "9.1.0", "9.0.0"])
        self.cfg.set("update.snooze_until", _time.time() - 1)                        # the day passed
        self.window._update_checked(self.newer, manual=False)
        self.assertEqual(len(self.asked), 4)


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
