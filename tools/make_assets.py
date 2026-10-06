"""Render the README / website images from the real widgets (offscreen, demo library).

    QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 python tools/make_assets.py OUTPUT_DIR

Nothing here touches the user's own library: it runs in a throw-away XDG tree.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="juke-assets-")
for _name, _sub in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
    os.environ[_name] = os.path.join(_TMP, _sub)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QFontDatabase, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath,  # noqa: E402
                           QRadialGradient)
from PySide6.QtWidgets import QApplication  # noqa: E402

from juke.assets import FONTS_DIR, ICON_SVG  # noqa: E402
from juke.audio.engine import AudioEngine  # noqa: E402
from juke.audio.equalizer import Equalizer  # noqa: E402
from juke.config import COVERS_DIR, Config, ensure_dirs  # noqa: E402
from juke.db.database import Database  # noqa: E402
from juke.gui import icons, styles  # noqa: E402
from juke.gui.main_window import MainWindow  # noqa: E402
from juke.gui.settings_dialog import SettingsDialog  # noqa: E402
from juke.i18n import translator  # noqa: E402

# Invented artists and albums so the screenshots never show anyone's real catalogue.
CATALOG = [
    ("Aurora Vale", "Glasshouse", "Indie Pop", ("Paper Moons", "Slow Motion Summer", "Glasshouse", "Northern Lights Café", "Pale Blue Static", "Hello, Golden Hour")),
    ("The Lantern Club", "After Hours in Color", "Rock", ("Neon Rain", "Cassette Heart", "Midnight Bus", "Faster Than Sleep", "Static & Sparks")),
    ("Delta & Rye", "Front Porch", "Americana", ("Front Porch", "Dust on the Dashboard", "Blue Ridge Morning", "Whiskey & Rain", "Long Way Home")),
    ("Nightjar", "Low Light", "Electronic", ("Signal Bloom", "Low Light", "Afterimage", "Ghost Frequency", "Glass Circuit")),
    ("Kōji Hara", "Quiet Rooms", "Ambient", ("Quiet Rooms", "Tatami Rain", "Snow on the Rails", "Slow Kettle")),
    ("Velvet Static", "Ultraviolet", "Synthpop", ("Ultraviolet", "Drive Me Somewhere", "Chrome Lovers", "Sunset Boulevard Blues", "Night Shift")),
    ("Copper & Pine", "Homestead", "Folk", ("Homestead", "Kitchen Table Hymn", "River Song", "Wildflower Road")),
    ("Sable Coast", "Salt Air", "Indie Rock", ("Salt Air", "Lighthouse", "Borrowed Time", "Tides")),
]
PALETTES = [("#7aa2f7", "#cba6f7"), ("#f38ba8", "#fab387"), ("#94e2d5", "#89b4fa"), ("#cba6f7", "#f5c2e7"),
            ("#a6e3a1", "#94e2d5"), ("#fab387", "#f9e2af"), ("#89b4fa", "#74c7ec"), ("#f5c2e7", "#f38ba8")]


def draw_cover(key: str, index: int) -> None:
    """A clean geometric cover (never a real album)."""
    rng = random.Random(index * 7919)
    a, b = (QColor(c) for c in PALETTES[index % len(PALETTES)])
    image = QImage(320, 320, QImage.Format_RGB32)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, 320, 320)
    g.setColorAt(0, a.darker(230))
    g.setColorAt(1, b.darker(170))
    p.fillRect(image.rect(), g)
    for _ in range(4):
        c = QColor(rng.choice((a, b)))
        c.setAlpha(rng.randint(60, 150))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        r = rng.randint(50, 130)
        p.drawEllipse(QPointF(rng.randint(30, 290), rng.randint(30, 290)), r, r)
    ring = QColor("#ffffff")
    ring.setAlpha(150)
    p.setPen(ring)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(160, 160), 72, 72)
    p.drawEllipse(QPointF(160, 160), 28, 28)
    p.end()
    image.save(str(COVERS_DIR / f"{key}.jpg"), "JPEG", 90)


def build_library(db: Database) -> None:
    rng = random.Random(4)
    rows, index = [], 0
    for a_i, (artist, album, genre, songs) in enumerate(CATALOG):
        key = f"demo{a_i}"
        draw_cover(key, a_i)
        for t_i, title in enumerate(songs, 1):
            index += 1
            remote = a_i in (2, 3, 5, 7)
            rows.append({
                "source_type": "airsonic" if remote else "local",
                "location": str(index) if remote else f"/demo/{index}.flac",
                "folder": f"{artist}/{album}" if remote else "",
                "title": title, "artist": artist, "album": album, "genre": genre, "year": 2016 + a_i,
                "track_no": t_i, "duration": float(rng.randint(151, 297)), "bitrate": rng.choice((320, 256, 1011, 320)),
                "cover_key": key,
            })
    db.upsert_many(rows)
    ids = db.query_ids()
    party = db.create_playlist("Night Drive")
    db.add_to_playlist(party, [ids[i] for i in (3, 9, 14, 20, 27, 31)])
    sunday = db.create_playlist("Sunday Morning")
    db.add_to_playlist(sunday, [ids[i] for i in (5, 11, 16, 22)])


def settle(ms: int) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def make_window(lang: str):
    translator.set_language(lang)
    cfg = Config(Path(_TMP) / f"settings-{lang}.json")
    cfg.set("scan_on_start", False)
    cfg.set("music_dirs", [])
    cfg.set("volume", 72)
    cfg.set("language", lang)
    db = Database(Path(_TMP) / "demo.db")
    if db.count() == 0:
        build_library(db)
    engine = AudioEngine()
    eq = Equalizer(cfg)
    window = MainWindow(cfg, db, engine, eq)
    window.avail.want = lambda tracks: None                    # the demo songs have no files: do not grey them out
    window._check_server = lambda force=False: None            # ...and there is no server to ask: Airsonic shows as connected
    window.avail.set_server(True)
    window.statusBar().clearMessage()
    window.resize(1320, 820)
    window.show()
    settle(150)
    return window, db, eq


def stage_playing(window, db) -> None:
    ids = db.query_ids(text="glasshouse")
    track = db.get_track(ids[2])
    everyone_ids = db.query_ids()
    from juke.gui.main_window import cover_path
    window.top_bar.set_track(track, __import__("PySide6.QtGui", fromlist=["QPixmap"]).QPixmap(str(cover_path(track.cover_key))))
    window.top_bar.set_state("playing")
    window.top_bar.set_position(102000, int(track.duration * 1000))
    window.current_track = track
    window.queue.set_context(db.query_ids(), track.id)
    if not db.playlists():                                     # two playlists, so "In playlists" has something to say
        everyone = db.query_ids()
        db.add_to_playlist(db.create_playlist("Road trip"), everyone[0:6])
        db.add_to_playlist(db.create_playlist("Sunday morning"), everyone[2:9])
        window.refresh_playlists()
        window.table.track_model.invalidate_rows()
    window.table.track_model.set_current(track.id)
    window.table.track_model.set_state("playing")
    window.table.track_model.set_animating(True)               # the bars beside the song that is on
    window.table.track_model._frame = 7
    for earlier in everyone_ids[:2] + everyone_ids[3:5]:                         # songs that already played: a green check
        window.table.track_model.mark_played(earlier)
    window._apply_crossfade(5)                                 # the green light under the volume
    window.table.selectRow(window.table.track_model.ids().index(track.id))
    window.setWindowTitle(window._window_title())


def grab(widget, path: Path) -> None:
    settle(1400)  # let the spectrum animate
    widget.grab().save(str(path), "PNG")
    print("wrote", path)


def rounded(image: QImage, radius: float) -> QImage:
    out = QImage(image.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(out.rect()), radius, radius)
    p.setClipPath(path)
    p.drawImage(0, 0, image)
    p.end()
    return out


def make_hero(shot: Path, out: Path, tagline: str, sub: str, chips: tuple[str, ...] = ()) -> None:
    """Wide banner: glow, app icon, wordmark, tagline and the real screenshot."""
    scale = 2
    w, h = 1280 * scale, 760 * scale
    canvas = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    bg = QLinearGradient(0, 0, 0, h)
    bg.setColorAt(0, QColor("#12121c"))
    bg.setColorAt(1, QColor("#0d0d15"))
    p.fillRect(canvas.rect(), bg)
    for cx, cy, r, color, alpha in ((0.28, 0.02, 0.55, "#7aa2f7", 70), (0.74, 0.0, 0.5, "#cba6f7", 60)):
        g = QRadialGradient(w * cx, h * cy, w * r)
        c = QColor(color)
        c.setAlpha(alpha)
        g.setColorAt(0, c)
        c.setAlpha(0)
        g.setColorAt(1, c)
        p.fillRect(canvas.rect(), g)

    icon = icons.render_svg(ICON_SVG.read_bytes(), 120 * scale, 1.0).toImage()
    p.drawImage(int(w / 2 - 60 * scale), 44 * scale, icon)
    from PySide6.QtGui import QFont
    font = QFont("Inter")
    font.setPixelSize(72 * scale // 1)
    font.setWeight(QFont.Bold)
    font.setLetterSpacing(QFont.AbsoluteSpacing, -1.5 * scale)
    p.setFont(font)
    title_rect = QRectF(0, 176 * scale, w, 84 * scale)
    grad = QLinearGradient(w / 2 - 130 * scale, 0, w / 2 + 130 * scale, 0)
    grad.setColorAt(0, QColor("#8fb1f9"))
    grad.setColorAt(1, QColor("#d6b8fa"))
    p.setPen(QColor("#ffffff"))
    p.drawText(title_rect, Qt.AlignHCenter | Qt.AlignVCenter, "Juke")
    from PySide6.QtGui import QFontMetrics
    word = QFontMetrics(font).horizontalAdvance("Juke")                       # the "1.0" pill sits at the end of the wordmark
    pill_font = QFont("Inter")
    pill_font.setPixelSize(26 * scale)
    pill_font.setWeight(QFont.Bold)
    pill = QRectF(w / 2 + word / 2 + 14 * scale, 190 * scale, 70 * scale, 40 * scale)
    pill_fill = QLinearGradient(pill.left(), 0, pill.right(), 0)
    pill_fill.setColorAt(0, QColor("#7aa2f7"))
    pill_fill.setColorAt(1, QColor("#cba6f7"))
    p.setPen(Qt.NoPen)
    p.setBrush(pill_fill)
    p.drawRoundedRect(pill, 20 * scale, 20 * scale)
    p.setFont(pill_font)
    p.setPen(QColor("#11111b"))
    p.drawText(pill, Qt.AlignCenter, "1.0")
    font.setPixelSize(24 * scale)
    font.setWeight(QFont.Medium)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0)
    p.setFont(font)
    p.setPen(QColor("#cdd6f4"))
    p.drawText(QRectF(0, 266 * scale, w, 34 * scale), Qt.AlignHCenter | Qt.AlignVCenter, tagline)
    font.setPixelSize(17 * scale)
    font.setWeight(QFont.Normal)
    p.setFont(font)
    p.setPen(QColor("#9399b2"))
    p.drawText(QRectF(0, 304 * scale, w, 26 * scale), Qt.AlignHCenter | Qt.AlignVCenter, sub)

    if chips:                                                                  # what is new, as a row of small badges
        chip_font = QFont("Inter")
        chip_font.setPixelSize(15 * scale)
        chip_font.setWeight(QFont.DemiBold)
        metrics = QFontMetrics(chip_font)
        pad, gap = 16 * scale, 10 * scale
        widths = [metrics.horizontalAdvance(c) + 2 * pad for c in chips]
        x0 = (w - (sum(widths) + gap * (len(chips) - 1))) / 2
        for text, cw in zip(chips, widths):
            box = QRectF(x0, 342 * scale, cw, 32 * scale)
            edge = QColor("#cba6f7")
            edge.setAlpha(90)
            fill = QColor("#cba6f7")
            fill.setAlpha(26)
            p.setPen(edge)
            p.setBrush(fill)
            p.drawRoundedRect(box, 16 * scale, 16 * scale)
            p.setFont(chip_font)
            p.setPen(QColor("#e4dcfb"))
            p.drawText(box, Qt.AlignCenter, text)
            x0 += cw + gap
    shot_img = QImage(str(shot))
    width = 1010 * scale
    scaled = shot_img.scaledToWidth(width, Qt.SmoothTransformation)
    card = rounded(scaled, 18 * scale)
    x, y = (w - width) // 2, 400 * scale
    for i in range(14):  # soft shadow
        shadow = QColor(0, 0, 0, 12)
        p.setPen(Qt.NoPen)
        p.setBrush(shadow)
        p.drawRoundedRect(QRectF(x - i * 3, y + 12 * scale - i * 2, width + i * 6, card.height() + i * 5), 24 * scale, 24 * scale)
    outline = QColor("#ffffff")
    outline.setAlpha(28)
    p.setBrush(Qt.NoBrush)
    p.setPen(outline)
    p.drawRoundedRect(QRectF(x, y, width, card.height()), 18 * scale, 18 * scale)
    p.drawImage(x, y, card)
    fade = QLinearGradient(0, h - 150 * scale, 0, h)
    fade.setColorAt(0, QColor(13, 13, 21, 0))
    fade.setColorAt(1, QColor(13, 13, 21, 255))
    p.fillRect(0, h - 150 * scale, w, 150 * scale, fade)
    p.end()
    canvas.save(str(out), "PNG")
    print("wrote", out)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "assets").resolve()
    out.mkdir(parents=True, exist_ok=True)
    ensure_dirs()
    app = QApplication.instance() or QApplication([])
    for font in FONTS_DIR.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    app.setStyle("Fusion")
    app.setPalette(styles.build_palette())
    app.setStyleSheet(styles.build_stylesheet())

    # English main window, playing
    window, db, eq = make_window("en")
    stage_playing(window, db)
    grab(window, out / "screenshot-main.png")

    # Internet radio: saved stations (invented names) and a live one on air
    from juke.db.database import Station
    for name, host, tags, country, codec, bitrate in (
            ("Radio Costa Brava", "costabrava", "salsa, tropical", "Dominican Republic", "AAC", 128),
            ("Latido FM 98.3", "latido", "pop, latino", "Colombia", "MP3", 128),
            ("Nocturna Jazz", "nocturna", "jazz, lounge", "Spain", "AAC", 64),
            ("Bachata Real", "bachatareal", "bachata", "Dominican Republic", "MP3", 96),
            ("Mundo Clásico", "mundo", "classical", "Mexico", "AAC", 128)):
        db.add_station(Station(0, name, f"https://{host}.example/stream", tags=tags, country=country, codec=codec, bitrate=bitrate))
    window._update_counts()
    live = db.stations()[3]
    window.current_station = live
    window.top_bar.set_station(live, None)
    window.top_bar.set_now_playing("Aurora Vale - Paper Moons")
    window.top_bar.set_state("playing")
    window.top_bar.set_position(184000, 0)
    window.sidebar.select("stations")
    window._show_view("stations", None)
    window.radio_view.set_playing_url(live.stream_url)
    grab(window, out / "screenshot-radio.png")
    window.current_station = None
    window.radio_view.set_playing_url(None)
    window.top_bar.lcd.clear()
    window.sidebar.select("all")
    window._show_view("all", None)
    stage_playing(window, db)

    # the same window in the light theme
    window.theme.apply("light")
    grab(window, out / "screenshot-light.png")
    window.theme.apply("dark")

    # queue view with "Play next" / "Add to queue" items
    ids = db.query_ids()
    window.queue.play_next([ids[20], ids[9]])
    window.queue.add_to_queue([ids[31], ids[4], ids[12]])
    window.sidebar.select("queue")
    window._show_view("queue", None)
    window.table.clearSelection()
    grab(window, out / "screenshot-queue.png")

    # Airsonic: the server's own folder hierarchy
    sidebar = window.sidebar
    sidebar._items[("airsonic", None)].setExpanded(True)
    for name in ("Delta & Rye", "Nightjar"):
        sidebar._items[("folder", name)].setExpanded(True)
    sidebar.select("folder", "Delta & Rye/Front Porch")
    window._show_view("folder", "Delta & Rye/Front Porch")
    window.table.clearSelection()
    grab(window, out / "screenshot-folders.png")
    sidebar.select("all")
    window._show_view("all", None)

    # a playlist: when songs go in, the date is not needed here, the ✓ in "Add to playlist" tells what is where
    first_list = db.playlists()[0][0]
    sidebar.select("playlist", first_list)
    window._show_view("playlist", first_list)
    window.table.clearSelection()
    grab(window, out / "screenshot-playlist.png")
    sidebar.select("all")
    window._show_view("all", None)

    # synced lyrics (invented words) beside the song that is playing
    stage_playing(window, db)
    demo = ("[00:08.00]Paper moons over the kitchen light\n[00:14.00]Slow motion summer, hold on tight\n"
            "[00:20.00]Glasshouse windows, golden hour\n[00:26.00]Every colour in the shower\n"
            "[00:32.00]We were never in a hurry\n[00:38.00]Hello, golden hour")
    playing = window.current_track
    window._save_lyrics(playing, demo)
    window._show_lyrics_panel(True)
    window.lyrics_panel.set_position(27000)
    window.lyrics_panel.set_lyrics(demo)
    window.lyrics_panel.set_position(27000)
    grab(window, out / "screenshot-lyrics.png")
    window._show_lyrics_panel(False)

    # equalizer
    eq.set_enabled(True)
    eq.load_preset("Rock")
    window.toggle_equalizer()
    dialog = window._eq_dialog
    dialog.move(0, 0)
    settle(200)
    grab(dialog, out / "screenshot-equalizer.png")
    window._eq_dialog.hide()

    # Airsonic settings tab
    window.config.set("airsonic", {"enabled": True, "url": "https://music.example.com", "username": "alex", "password": "demo"})
    settings = SettingsDialog(window.config, True, window)
    settings.findChild(__import__("PySide6.QtWidgets", fromlist=["QTabWidget"]).QTabWidget).setCurrentIndex(3)
    settings.show()
    settle(200)
    grab(settings, out / "screenshot-settings.png")
    settings.findChild(__import__("PySide6.QtWidgets", fromlist=["QTabWidget"]).QTabWidget).setCurrentIndex(1)
    settle(150)
    grab(settings, out / "screenshot-playback.png")
    settings.reject()
    window.close()

    # Spanish main window
    window, db, eq = make_window("es")
    stage_playing(window, db)
    grab(window, out / "screenshot-main-es.png")
    window.close()

    make_hero(out / "screenshot-main.png", out / "hero.png",
              "A modern music player for Linux", "Three panes. Airsonic streaming. Internet radio. Instant with 50,000+ tracks.",
              ("Media keys", "Crossfade", "Lyrics in any language", "An equalizer for everyone"))
    translator.set_language("es")
    make_hero(out / "screenshot-main-es.png", out / "hero-es.png",
              "Un reproductor de música moderno para Linux", "Tres paneles. Streaming Airsonic. Radio por Internet. Instantáneo con más de 50.000 pistas.",
              ("Teclas multimedia", "Crossfade", "Letras en cualquier idioma", "Un ecualizador para todos"))

    svg = ICON_SVG.read_bytes()
    icons.render_svg(svg, 512, 1.0).save(str(out / "icon.png"), "PNG")
    print("done")


if __name__ == "__main__":
    main()
