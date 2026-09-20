"""Main window: top bar, sidebar and song table, plus the glue between them."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, QThread, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QSizePolicy, QSplitter, QToolButton, QVBoxLayout, QWidget)

from .. import REPO_URL, __version__, integration
from ..api.airsonic import AirsonicClient, normalize_base_url
from ..audio.engine import AudioEngine
from ..audio.equalizer import Equalizer
from ..audio.queue import PlayQueue
from ..audio.sources import SourceError, SourceResolver
from ..config import AUDIO_EXTENSIONS, Config
from ..db.database import SOURCE_AIRSONIC, SOURCE_LOCAL, Database, Scope, Track
from ..db.indexer import LibraryScanner, cover_key_for, cover_path, extract_cover, read_tags, save_cover
from ..i18n import tr, translator, trn
from ..power import on_battery
from ..workers import AsyncWorker
from . import icons, styles
from .components.sidebar import Sidebar
from .components.top_bar import TopBar
from .components.track_table import TrackTable
from .dialogs import ask_text, confirm, notice

MAX_CONSECUTIVE_ERRORS = 4


def format_total(seconds: float) -> str:
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


class MainWindow(QMainWindow):
    def __init__(self, config: Config, db: Database, engine: AudioEngine, equalizer: Equalizer) -> None:
        super().__init__()
        self.config, self.db, self.engine, self.equalizer = config, db, engine, equalizer
        self.queue = PlayQueue()
        self.queue.shuffle = bool(config.get("shuffle"))
        self.queue.repeat = config.get("repeat")
        self.resolver = SourceResolver(lambda: self.airsonic)
        self.airsonic: AirsonicClient | None = None   # only builds URLs; I/O uses per-task clients
        self.current_track: Track | None = None
        self._view: tuple[str, object] = ("all", None)
        self._scanner: LibraryScanner | None = None
        self._sync_worker: AsyncWorker | None = None
        self._workers: set[AsyncWorker] = set()
        self._eq_dialog: EqualizerDialog | None = None
        self._playlists: list[tuple[int, str, int]] = []
        self._empty_action = ""
        self._errors_in_a_row = 0
        self._warned_no_vlc = False
        self._live_refresh = False
        self._last_live_refresh = 0.0

        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(1000, 620)
        self.resize(1320, 820)

        self.top_bar = TopBar()
        self.sidebar = Sidebar()
        self.table = TrackTable(db)
        self.title_label = QLabel()
        self.title_label.setObjectName("heading")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("muted")
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(300)
        self.search.addAction(icons.icon("search", styles.MUTED, size=18), QLineEdit.LeadingPosition)
        self.menu_button = QToolButton()
        self.menu_button.setObjectName("menuButton")
        self.menu_button.setIcon(icons.icon("more", styles.TEXT))
        self.menu_button.setFixedSize(38, 38)
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        self.menu_button.setCursor(Qt.PointingHandCursor)

        heading = QVBoxLayout()
        heading.setSpacing(2)
        heading.addWidget(self.title_label)
        heading.addWidget(self.subtitle_label)
        header = QHBoxLayout()
        header.setContentsMargins(22, 16, 18, 10)
        header.setSpacing(12)
        header.addLayout(heading, 1)
        header.addWidget(self.search)
        header.addWidget(self.menu_button)
        main_view = QWidget()
        main_view.setObjectName("mainView")
        column = QVBoxLayout(main_view)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addLayout(header)
        column.addWidget(self.table, 1)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.settings_button = QToolButton()
        self.settings_button.setObjectName("sidebarSettings")
        self.settings_button.setIcon(icons.icon("gear", styles.SUBTEXT, active=styles.TEXT, size=18))
        self.settings_button.setIconSize(QSize(18, 18))
        self.settings_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.settings_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.clicked.connect(lambda: self.open_settings())
        footer = QHBoxLayout()
        footer.setContentsMargins(8, 4, 8, 12)
        footer.addWidget(self.settings_button)
        side = QWidget()
        side.setObjectName("sidebarPanel")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)
        side_layout.addWidget(self.sidebar, 1)
        side_layout.addLayout(footer)
        self.splitter.addWidget(side)
        self.splitter.addWidget(main_view)
        self.splitter.setStretchFactor(1, 1)
        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.top_bar)
        root.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

        self.status_label = QLabel()
        self.progress = QProgressBar()
        self.progress.setFixedWidth(180)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().addPermanentWidget(self.status_label)
        self.statusBar().addPermanentWidget(self.progress)

        self._power_timer = QTimer(self)
        self._power_timer.setTimerType(Qt.VeryCoarseTimer)
        self._power_timer.setInterval(30_000)
        self._power_timer.timeout.connect(self._update_activity)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(140)
        self._search_timer.timeout.connect(self._apply_search)
        self.search.textChanged.connect(lambda _: self._search_timer.start())

        self._wire()
        self._restore_state()
        self.retranslate()
        self._configure_airsonic()
        self.refresh_library()
        self.sidebar.select("all")
        self._show_view("all", None)
        QTimer.singleShot(2500, self._startup_tasks)   # let the window appear before any disk work

    # ------------------------------------------------------------------------------ wiring
    def _wire(self) -> None:
        tb, eng = self.top_bar, self.engine
        tb.play_clicked.connect(self._play_pressed)
        tb.next_clicked.connect(lambda: self._advance(auto=False))
        tb.prev_clicked.connect(self._previous)
        tb.stop_clicked.connect(self._stop)
        tb.seek_requested.connect(eng.seek)
        tb.volume_changed.connect(eng.set_volume)
        tb.mute_toggled.connect(eng.set_muted)
        tb.eq_clicked.connect(self.toggle_equalizer)
        tb.shuffle_toggled.connect(self._set_shuffle)
        tb.repeat_changed.connect(self._set_repeat)
        eng.state_changed.connect(tb.set_state)
        eng.state_changed.connect(lambda _s: self._update_activity())
        eng.position_changed.connect(tb.set_position)
        eng.track_finished.connect(self._track_finished)
        eng.error.connect(self._engine_error)
        self.sidebar.selected.connect(self._show_view)
        t = self.table
        t.play_requested.connect(self._play_from_table)
        t.play_next_requested.connect(self._play_next)
        t.queue_requested.connect(self._add_to_queue)
        t.remove_from_queue_requested.connect(self._remove_from_queue)
        t.favorite_requested.connect(self._set_favorite)
        t.edit_requested.connect(self._edit_metadata)
        t.add_to_playlist_requested.connect(self._add_to_playlist)
        t.new_playlist_requested.connect(self._new_playlist)
        t.remove_from_playlist_requested.connect(self._remove_from_playlist)
        t.action_requested.connect(self._run_empty_action)
        self.sidebar.new_playlist_requested.connect(lambda: self._new_playlist())
        self.sidebar.rename_playlist_requested.connect(self._rename_playlist)
        self.sidebar.delete_playlist_requested.connect(self._delete_playlist)
        translator.changed.connect(self.retranslate)
        QGuiApplication.instance().applicationStateChanged.connect(lambda _state: self._update_activity())

        for keys, slot in (("Space", self._play_pressed), ("Ctrl+F", lambda: (self.search.setFocus(), self.search.selectAll())),
                           ("Ctrl+E", self.toggle_equalizer), ("Ctrl+,", self.open_settings),
                           ("Ctrl+Right", lambda: self._advance(auto=False)), ("Ctrl+Left", self._previous),
                           ("Ctrl+Q", self.close), ("Ctrl+N", lambda: self._new_playlist())):
            QShortcut(QKeySequence(keys), self).activated.connect(slot)

    def _restore_state(self) -> None:
        window = self.config.get("window")
        if window.get("geometry"):
            self.restoreGeometry(bytes.fromhex(window["geometry"]))
        sizes = window.get("splitter")
        if isinstance(sizes, list) and len(sizes) == 2:
            self.splitter.setSizes([int(s) for s in sizes])
        volume, muted = int(self.config.get("volume")), bool(self.config.get("muted"))
        self.engine.volume, self.engine.muted = volume, muted
        self.top_bar.set_volume(volume, muted)
        self.top_bar.set_shuffle(self.queue.shuffle)
        self.top_bar.set_repeat(self.queue.repeat)
        self.top_bar.set_state("stopped")
        self.engine.attach_equalizer(self.equalizer)

    def save_state(self) -> None:
        self.config.set("window.geometry", bytes(self.saveGeometry()).hex())
        self.config.set("window.splitter", self.splitter.sizes())
        self.config.set("volume", self.engine.volume)
        self.config.set("muted", self.engine.muted)
        self.config.set("shuffle", self.queue.shuffle)
        self.config.set("repeat", self.queue.repeat)
        self.config.save()

    # ------------------------------------------------------------------------------ power
    def _meter_allowed(self) -> bool:
        mode = self.config.get("meter")
        return mode == "on" or (mode != "off" and not on_battery())

    def _update_activity(self) -> None:
        """Nobody watches a hidden window: slow the poll and freeze the level meter (and always
        freeze it on battery unless the user asked for it)."""
        active = self.isVisible() and not self.isMinimized() and \
            QGuiApplication.applicationState() == Qt.ApplicationActive
        self.engine.set_ui_active(active)
        self.top_bar.set_animating(active and self._meter_allowed())
        if active and self.config.get("meter") == "auto" and self.engine.state == "playing":
            self._power_timer.start()     # the charger may be plugged in or out while we play
        else:
            self._power_timer.stop()

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.WindowStateChange:
            self._update_activity()
        super().changeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._update_activity()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._update_activity()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.save_state()
        if self._scanner is not None:
            self._scanner.cancel()
            self._scanner.wait(4000)
        for worker in list(self._workers) + ([self._sync_worker] if self._sync_worker else []):
            worker.cancel()
            worker.wait(2000)
        self.engine.shutdown()
        super().closeEvent(event)

    # ------------------------------------------------------------------------------ text
    def retranslate(self) -> None:
        self.search.setPlaceholderText(tr("search.placeholder"))
        self.menu_button.setToolTip(tr("menu.more"))
        self.settings_button.setText("\u2002\u2002" + tr("sidebar.settings"))  # en-spaces: air between icon and label
        self.sidebar.retranslate()
        self.top_bar.retranslate()
        self.table.track_model.refresh_headers()
        self._build_menu()
        self._update_heading()
        if self._eq_dialog:
            self._eq_dialog.retranslate()
        self.setWindowTitle(self._window_title())

    def _build_menu(self) -> None:
        menu = QMenu(self)

        def add(label: str, slot, hint: str = "") -> QAction:
            action = menu.addAction(f"{label}\t{hint}" if hint else label)
            action.triggered.connect(slot)
            return action

        add(tr("menu.new_playlist"), lambda: self._new_playlist(), "Ctrl+N")
        add(tr("menu.equalizer"), self.toggle_equalizer, "Ctrl+E")
        menu.addSeparator()
        add(tr("menu.rescan"), self.start_scan)
        self.sync_action = add(tr("menu.sync_airsonic"), self.sync_airsonic)
        self.sync_action.setEnabled(self.airsonic is not None)
        menu.addSeparator()
        add(tr("menu.settings"), self.open_settings, "Ctrl+,")
        add(tr("menu.about"), self.show_about)
        menu.addSeparator()
        add(tr("menu.quit"), self.close, "Ctrl+Q")
        self.menu_button.setMenu(menu)
        self._menu = menu

    def _window_title(self) -> str:
        t = self.current_track
        return f"{t.title} — {t.artist or tr('unknown_artist')} · Juke" if t else "Juke"

    def notify(self, message: str, ms: int = 5000) -> None:
        self.statusBar().showMessage(message, ms)

    # ------------------------------------------------------------------------------ library views
    def refresh_library(self) -> None:
        """Re-read groups/counts and reload the current view after the library changed."""
        db = self.db
        self.sidebar.set_groups(db.distinct("artist"), db.distinct("album"), db.distinct("genre"))
        self.sidebar.set_folders(db.folders(SOURCE_AIRSONIC))
        self._update_counts()
        self.refresh_playlists()
        self._reload_view()
        self._update_heading()

    def _reload_view(self) -> None:
        """Re-run the current view (playlists and the queue hold explicit id lists)."""
        key, value = self._view
        if key == "playlist":
            self.table.track_model.set_fixed_ids(self.db.playlist_track_ids(value))
        elif key == "queue":
            self.table.track_model.set_fixed_ids(self.queue.view())
        else:
            self.table.track_model.reload()

    def _update_counts(self) -> None:
        db = self.db
        self.sidebar.set_counts(
            all=db.count(), airsonic=db.count(SOURCE_AIRSONIC), favorites=db.count_favorites(),
            queue=len(self.queue.view()) or None,
        )

    def _scope_for(self, key: str, value: object) -> tuple[Scope, list[int] | None, str | None]:
        if key == "artist":
            return Scope(artist=value), None, None
        if key == "album":
            return Scope(album=value), None, None
        if key == "genre":
            return Scope(genre=value), None, None
        if key == "folder":
            return Scope(source_type=SOURCE_AIRSONIC, folder=str(value)), None, None
        if key == "playlist":
            return Scope(), self.db.playlist_track_ids(int(value)), None
        return {
            "albums": (Scope(), None, "album"),
            "genres": (Scope(), None, "genre"),
            "airsonic": (Scope(source_type=SOURCE_AIRSONIC), None, None),
            "favorites": (Scope(favorites=True), None, None),
            "recent": (Scope(recent=True), None, None),
            "queue": (Scope(), self.queue.view(), None),
        }.get(key, (Scope(), None, None))

    def _show_view(self, key: str, value: object) -> None:
        self._view = (key, value)
        scope, fixed, sort = self._scope_for(key, value)
        self.table.queue_mode = key == "queue"
        self.table.playlist_mode = key == "playlist"
        self.table.show_view(scope, fixed, sort)
        self.table.track_model.set_current(self.current_track.id if self.current_track else None)
        self._update_heading()
        if key == "airsonic" and self.airsonic and self.db.count(SOURCE_AIRSONIC) == 0 and self._sync_worker is None:
            self.sync_airsonic()

    def _apply_search(self) -> None:
        self.table.track_model.set_text(self.search.text())
        self._update_heading()

    def _view_title(self) -> str:
        key, value = self._view
        if key in ("artist", "album", "genre"):
            return str(value) or tr("unknown_" + key)
        if key == "folder":
            return str(value).rsplit("/", 1)[-1]
        if key == "playlist":
            return next((name for pid, name, _ in self._playlists if pid == value), "")
        return tr({"all": "sidebar.all", "artists": "sidebar.artists", "albums": "sidebar.albums",
                   "genres": "sidebar.genres", "airsonic": "sidebar.airsonic", "favorites": "sidebar.favorites",
                   "recent": "sidebar.recent", "queue": "sidebar.queue"}.get(key, "sidebar.all"))

    def _update_heading(self) -> None:
        self.title_label.setText(self._view_title())
        model = self.table.track_model
        count = model.rowCount()
        text = trn("summary.songs", count)
        key = self._view[0]
        if count and key not in ("queue", "playlist"):
            scope, _fixed, _ = self._scope_for(*self._view)
            _, seconds = self.db.summary(scope, self.search.text())
            if seconds:
                text += " · " + format_total(seconds)
        if key == "folder":
            text = f"{self._view[1]} · {text}"  # full server path, like a breadcrumb
        self.subtitle_label.setText(text)
        self._update_empty_text()

    def _update_empty_text(self) -> None:
        key = self._view[0]
        action, kind = "", ""
        if self.search.text().strip():
            title, hint = tr("empty.search.title"), tr("empty.search.hint")
        elif key == "airsonic":
            if self.airsonic is None:
                title, hint = tr("empty.airsonic.title"), tr("empty.airsonic.hint")
                action, kind = tr("empty.airsonic.action"), "settings:2"
            elif self._sync_worker is not None:
                title, hint = tr("empty.syncing"), ""
            else:
                title, hint = tr("empty.airsonic_none.title"), tr("empty.airsonic_none.hint")
                action, kind = tr("menu.sync_airsonic"), "sync"
        elif key == "favorites":
            title, hint = tr("empty.favorites.title"), tr("empty.favorites.hint")
        elif key == "recent":
            title, hint = tr("empty.recent.title"), tr("empty.recent.hint")
        elif key == "queue":
            title, hint = tr("empty.queue.title"), tr("empty.queue.hint")
        elif key == "playlist":
            title, hint = tr("empty.playlist.title"), tr("empty.playlist.hint")
        elif self.db.count() == 0:
            title, hint = tr("empty.library.title"), tr("empty.library.hint")
            action, kind = tr("empty.library.action"), "settings:1"
        else:
            title, hint = "", ""
        self._empty_action = kind
        self.table.set_empty_text(title, hint, action)

    def _run_empty_action(self) -> None:
        if self._empty_action.startswith("settings:"):
            self.open_settings(int(self._empty_action.split(":")[1]))
        elif self._empty_action == "sync":
            self.sync_airsonic()

    # ------------------------------------------------------------------------------ playback
    def _play_from_table(self, track_id: int) -> None:
        self.queue.set_context(self.table.track_model.ids(), track_id)
        self._start(track_id)

    def _start(self, track_id: int) -> None:
        track = self.db.get_track(track_id)
        if track is None:
            self._skip_after_error(tr("msg.track_gone"))
            return
        try:
            url = self.resolver.resolve(track)
        except SourceError as exc:
            reason = tr("msg.airsonic_not_configured") if str(exc) == "airsonic" else tr("msg.file_missing", path=str(exc))
            self._skip_after_error(reason)
            return
        if not self.engine.play_url(url):
            return
        self._errors_in_a_row = 0
        self.queue.current = track_id
        self.current_track = track
        self.db.record_start(track_id)
        self.table.track_model.set_current(track_id)
        self.top_bar.set_track(track, self._cover_for(track))
        self.setWindowTitle(self._window_title())
        self._update_counts()
        self._refresh_queue_view()

    def _skip_after_error(self, reason: str) -> None:
        self._errors_in_a_row += 1
        self.notify(reason)
        if self._errors_in_a_row < MAX_CONSECUTIVE_ERRORS:
            QTimer.singleShot(400, lambda: self._advance(auto=True))
        else:
            self._errors_in_a_row = 0
            self.engine.stop()

    def _advance(self, auto: bool) -> None:
        next_id = self.queue.next(auto=auto)
        if next_id is None:
            self.engine.stop()
            self._playback_ended()
            return
        self._start(next_id)

    def _playback_ended(self) -> None:
        self.top_bar.lcd.clear()
        self.current_track = None
        self.table.track_model.set_current(None)
        self.setWindowTitle("Juke")

    def _previous(self) -> None:
        if self.queue.current is None:
            return
        if self.engine.position_ms() > 3000 or not self.queue.history:
            self.engine.seek(0.0)
            return
        previous = self.queue.previous()
        if previous is not None:
            self._start(previous)

    def _play_pressed(self) -> None:
        if self.engine.state in ("playing", "paused"):
            self.engine.toggle_pause()
            return
        selected = self.table.selected_ids()
        if selected:
            self._play_from_table(selected[0])
        elif self.queue.current is not None:
            self._start(self.queue.current)
        else:
            first = self.table.track_model.id_at(0)
            if first is not None:
                self._play_from_table(first)

    def _stop(self) -> None:
        self.engine.stop()

    def _track_finished(self) -> None:
        track = self.current_track
        if track is not None:
            self.db.record_completed(track.id)
            if track.source_type == SOURCE_AIRSONIC and self.airsonic is not None:
                self._airsonic_task(lambda client, _p: client.scrobble(track.location), quiet=True)
        self._advance(auto=True)

    def _engine_error(self, message: str) -> None:
        if not self.engine.available:
            if not self._warned_no_vlc:
                self._warned_no_vlc = True
                notice(self, tr("msg.no_vlc_title"), tr("msg.no_vlc"))
            return
        self._skip_after_error(tr("msg.playback_error"))

    def _set_shuffle(self, enabled: bool) -> None:
        self.queue.set_shuffle(enabled)
        self._refresh_queue_view()

    def _set_repeat(self, mode: str) -> None:
        self.queue.repeat = mode

    # ------------------------------------------------------------------------------ queue
    def _play_next(self, ids: list[int]) -> None:
        self.queue.play_next(ids)
        self._queue_changed(trn("msg.play_next", len(ids)))

    def _add_to_queue(self, ids: list[int]) -> None:
        self.queue.add_to_queue(ids)
        self._queue_changed(trn("msg.added_queue", len(ids)))

    def _remove_from_queue(self, ids: list[int]) -> None:
        self.queue.remove_from_queue(ids)
        self._queue_changed(None)

    def _queue_changed(self, message: str | None) -> None:
        if message:
            self.notify(message, 3000)
        if self.queue.current is None and self.engine.state == "stopped" and self.queue.user:
            self._advance(auto=False)  # nothing is playing: start the queue right away
            return
        self._update_counts()
        self._refresh_queue_view()

    def _refresh_queue_view(self) -> None:
        if self._view[0] == "queue":
            self.table.track_model.set_fixed_ids(self.queue.view())
            self._update_heading()

    # ------------------------------------------------------------------------------ playlists
    def refresh_playlists(self) -> None:
        self._playlists = self.db.playlists()
        self.sidebar.set_playlists(self._playlists)
        self.table.set_playlists([(pid, name) for pid, name, _ in self._playlists])

    def _unique_playlist_name(self, name: str, ignore: int | None = None) -> str:
        taken = {n.casefold() for pid, n, _ in self._playlists if pid != ignore}
        candidate, n = name, 2
        while candidate.casefold() in taken:
            candidate, n = f"{name} ({n})", n + 1
        return candidate

    def _new_playlist(self, ids: list[int] | None = None) -> None:
        name = ask_text(self, tr("playlist.new_title"), tr("playlist.name_prompt"), tr("playlist.default_name"))
        if not name:
            return
        name = self._unique_playlist_name(name)
        playlist_id = self.db.create_playlist(name)
        if ids:
            self.db.add_to_playlist(playlist_id, ids)
        self.refresh_playlists()
        self.sidebar.select("playlist", playlist_id)
        self._show_view("playlist", playlist_id)
        if ids:
            self.notify(trn("msg.added_playlist", len(ids), name=name), 3500)

    def _rename_playlist(self, playlist_id: int) -> None:
        current = next((n for pid, n, _ in self._playlists if pid == playlist_id), "")
        name = ask_text(self, tr("playlist.rename_title"), tr("playlist.name_prompt"), current)
        if not name or name == current:
            return
        self.db.rename_playlist(playlist_id, self._unique_playlist_name(name, ignore=playlist_id))
        self.refresh_playlists()
        self._update_heading()

    def _delete_playlist(self, playlist_id: int) -> None:
        name = next((n for pid, n, _ in self._playlists if pid == playlist_id), "")
        if not confirm(self, tr("playlist.delete_title"), tr("playlist.delete_text", name=name)):
            return
        self.db.delete_playlist(playlist_id)
        self.refresh_playlists()
        if self._view == ("playlist", playlist_id):
            self.sidebar.select("all")
            self._show_view("all", None)

    def _add_to_playlist(self, playlist_id: int, ids: list[int]) -> None:
        self.db.add_to_playlist(playlist_id, ids)
        name = next((n for pid, n, _ in self._playlists if pid == playlist_id), "")
        self.refresh_playlists()
        if self._view == ("playlist", playlist_id):
            self._reload_view()
            self._update_heading()
        self.notify(trn("msg.added_playlist", len(ids), name=name), 3500)

    def _remove_from_playlist(self, ids: list[int]) -> None:
        if self._view[0] != "playlist":
            return
        self.db.remove_from_playlist(self._view[1], ids)
        self.refresh_playlists()
        self._reload_view()
        self._update_heading()

    # ------------------------------------------------------------------------------ favourites / metadata
    def _set_favorite(self, ids: list[int], value: bool) -> None:
        self.db.set_favorite(ids, value)
        self._update_counts()
        if self._view[0] == "favorites":
            self.table.track_model.reload()
            self._update_heading()
        else:
            self.table.track_model.invalidate_rows()

    def _edit_metadata(self, track_id: int) -> None:
        track = self.db.get_track(track_id)
        if track is None or not track.is_local:
            return
        from .meta_dialog import MetadataDialog

        if MetadataDialog(track, self.db, self).exec():
            self.refresh_library()

    # ------------------------------------------------------------------------------ covers
    def _cover_for(self, track: Track) -> QPixmap | None:
        if track.cover_key:
            path = cover_path(track.cover_key)
            if path.exists():
                return QPixmap(str(path))
            if track.source_type == SOURCE_AIRSONIC and track.cover_key.startswith("as_") and self.airsonic:
                self._fetch_airsonic_cover(track)
        return None

    def _fetch_airsonic_cover(self, track: Track) -> None:
        cover_id, key = track.cover_key[3:], track.cover_key

        async def fetch(client: AirsonicClient, _progress) -> str:
            data = await client.get_cover_art(cover_id, 320)
            return key if save_cover(key, data) else ""

        def done(saved: str) -> None:
            if saved and self.current_track and self.current_track.cover_key == saved:
                self.top_bar.lcd.set_cover(QPixmap(str(cover_path(saved))))

        self._airsonic_task(fetch, on_result=done, quiet=True)

    # ------------------------------------------------------------------------------ scanning
    def _startup_tasks(self) -> None:
        if self.config.get("scan_on_start") or self.db.count(SOURCE_LOCAL) == 0:
            self.start_scan()
        if integration.is_installed():
            if integration.needs_refresh():
                integration.install()  # the AppImage moved or was updated: keep the menu entry valid
        elif integration.appimage_path() and not self.config.get("desktop_integration.asked"):
            self._offer_integration()

    def start_scan(self) -> None:
        if self._scanner is not None and self._scanner.isRunning():
            return
        dirs = [d for d in self.config.get("music_dirs", []) if Path(d).is_dir()]
        if not dirs:
            self.notify(tr("msg.no_folders"))
            return
        self._live_refresh = self.db.count(SOURCE_LOCAL) == 0
        self._last_live_refresh = time.monotonic()
        self._scanner = LibraryScanner(self.db, dirs, self)
        self._scanner.progress.connect(self._scan_progress)
        self._scanner.scan_finished.connect(self._scan_finished)
        self._scanner.failed.connect(lambda msg: self.notify(tr("msg.scan_failed", error=msg)))
        self._scanner.finished.connect(self._scan_thread_done)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status_label.setText(tr("status.scanning"))
        self._scanner.start(QThread.LowPriority)       # never compete with playback or the UI

    def _scan_progress(self, done: int, total: int) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        self.status_label.setText(tr("status.scanning_n", done=f"{done:,}", total=f"{total:,}"))
        if self._live_refresh and time.monotonic() - self._last_live_refresh > 3.0:
            self._last_live_refresh = time.monotonic()
            self.refresh_library()

    def _scan_finished(self, changed: int, removed: int, seen: int) -> None:
        self.refresh_library()
        self.queue.discard_missing(set(self.db.query_ids()))
        self.notify(tr("msg.scan_done", changed=f"{changed:,}", removed=f"{removed:,}"))

    def _scan_thread_done(self) -> None:
        self.progress.hide()
        self.status_label.clear()
        self._scanner = None

    # ------------------------------------------------------------------------------ Airsonic
    def _configure_airsonic(self) -> None:
        cfg = self.config.get("airsonic")
        if cfg["enabled"] and normalize_base_url(cfg["url"]) and cfg["username"]:
            self.airsonic = AirsonicClient(cfg["url"], cfg["username"], cfg["password"], auth=cfg.get("auth", "auto"))
        else:
            self.airsonic = None
        if hasattr(self, "sync_action"):
            self.sync_action.setEnabled(self.airsonic is not None)

    def _airsonic_task(self, operation, on_result=None, on_error=None, on_progress=None, quiet: bool = False) -> AsyncWorker | None:
        """Run ``operation(client, progress)`` on a worker with its own client and event loop."""
        cfg = self.config.get("airsonic")
        if self.airsonic is None:
            return None

        detected: dict[str, str] = {}

        async def factory(progress):
            client = AirsonicClient(cfg["url"], cfg["username"], cfg["password"], auth=cfg.get("auth", "auto"))
            try:
                return await operation(client, progress)
            finally:
                detected["auth"] = client.auth_mode
                await client.aclose()

        worker = AsyncWorker(factory, self)
        self._workers.add(worker)
        worker.finished.connect(lambda: self._remember_auth(detected.get("auth")))
        if on_result:
            worker.result.connect(on_result)
        if on_progress:
            worker.progress.connect(on_progress)
        if on_error:
            worker.failed.connect(on_error)
        elif not quiet:
            worker.failed.connect(lambda msg: self.notify(tr("msg.airsonic_error", error=msg)))
        worker.finished.connect(lambda w=worker: (self._workers.discard(w), w.deleteLater()))
        worker.start()
        return worker

    def _remember_auth(self, mode: str | None) -> None:
        """The server may only accept the password (not tokens): keep that so stream URLs match."""
        if mode and self.airsonic is not None and self.config.get("airsonic.auth") != mode:
            self.config.set("airsonic.auth", mode)
            self.config.save()
            self.airsonic.auth_mode = mode

    def sync_airsonic(self) -> None:
        if self.airsonic is None:
            self.notify(tr("msg.airsonic_not_configured"))
            return
        if self._sync_worker is not None:
            return
        db = self.db

        async def sync(client: AirsonicClient, progress) -> int:
            rows = await client.sync_library(progress)
            try:  # written from this worker thread so the UI never waits on the database
                db.replace_source(SOURCE_AIRSONIC, rows)
            finally:
                db.close_thread_connection()
            return len(rows)

        self.progress.setRange(0, 0)
        self.progress.show()
        self.status_label.setText(tr("status.syncing"))
        self._sync_worker = self._airsonic_task(
            sync, on_result=self._sync_done, on_error=self._sync_failed,
            on_progress=lambda n: self.status_label.setText(tr("status.syncing_n", n=f"{n:,}")),
        )
        if self._sync_worker is None:
            self._sync_finished_ui()
        else:
            self._sync_worker.finished.connect(self._sync_finished_ui)
        self._update_empty_text()

    def _sync_done(self, count: int) -> None:
        self.refresh_library()
        self.notify(tr("msg.sync_done", n=f"{count:,}"))

    def _sync_failed(self, message: str) -> None:
        self.notify(tr("msg.airsonic_error", error=message), 8000)

    def _sync_finished_ui(self) -> None:
        self._sync_worker = None
        if not (self._scanner and self._scanner.isRunning()):
            self.progress.hide()
            self.status_label.clear()
        self._update_empty_text()
        self.table.viewport().update()

    # ------------------------------------------------------------------------------ dialogs
    def toggle_equalizer(self) -> None:
        from .components.eq_dialog import EqualizerDialog

        if self._eq_dialog is None:
            self._eq_dialog = EqualizerDialog(self.equalizer, self.engine, self)
            self._eq_dialog.closed.connect(lambda: self.top_bar.set_eq_open(False))
        if self._eq_dialog.isVisible():
            self._eq_dialog.hide()
            self.top_bar.set_eq_open(False)
        else:
            self._eq_dialog.show()
            self._eq_dialog.raise_()
            self.top_bar.set_eq_open(True)

    def open_settings(self, tab: int = 0) -> None:
        from .settings_dialog import SettingsDialog

        dialog = SettingsDialog(self.config, integration.is_installed(), self, int(tab))
        if not dialog.exec():
            return
        old_dirs = list(self.config.get("music_dirs", []))
        old_airsonic = dict(self.config.get("airsonic"))
        dialog.apply_to(self.config)
        self.config.save()
        translator.set_language(self.config.get("language"))
        if dialog.wants_integration != integration.is_installed():
            self._set_integration(dialog.wants_integration)
        self._configure_airsonic()
        self._update_activity()
        if self.config.get("music_dirs") != old_dirs:
            self.start_scan()
        if self.config.get("airsonic") != old_airsonic and self.airsonic is not None:
            self.sync_airsonic()
        self._update_empty_text()

    def _offer_integration(self) -> None:
        self.config.set("desktop_integration.asked", True)
        self._set_integration(confirm(self, tr("integration.title"), tr("integration.text")))
        self.config.save()

    def _set_integration(self, enabled: bool) -> None:
        self.config.set("desktop_integration.enabled", enabled)
        try:
            integration.install() if enabled else integration.uninstall()
            self.notify(tr("integration.done") if enabled else tr("integration.removed"))
        except OSError as exc:
            self.notify(tr("integration.failed", error=str(exc)), 8000)

    def show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("menu.about"))
        box.setIconPixmap(icons.render_svg((Path(__file__).resolve().parent.parent / "assets" / "juke.svg").read_bytes(), 72))
        box.setText(f"<h3>Juke {__version__}</h3>")
        box.setInformativeText(f"{tr('about.text')}<br><br><a href='{REPO_URL}'>{REPO_URL}</a>")
        box.setTextFormat(Qt.RichText)
        box.exec()

    # ------------------------------------------------------------------------------ opening files
    def open_paths(self, paths: list[str]) -> None:
        """Play files handed over by the desktop ("Open with Juke" / command line)."""
        files: list[str] = []
        for raw in paths:
            local = QUrl(raw).toLocalFile() if raw.startswith("file:") else raw
            if Path(local).suffix.lower() in AUDIO_EXTENSIONS and Path(local).is_file():
                files.append(str(Path(local).resolve()))
        rows = []
        for path in files:
            tags = read_tags(path)
            if tags:
                stat = Path(path).stat()
                key = cover_key_for(tags["artist"], tags["album"], path)
                if not cover_path(key).exists():
                    data = extract_cover(path)
                    key = key if data and save_cover(key, data) else ""
                rows.append({"source_type": SOURCE_LOCAL, "location": path, "cover_key": key,
                             "mtime": stat.st_mtime, "size": stat.st_size, **tags})
        if not rows:
            return
        self.db.upsert_many(rows)
        ids = [t.id for t in (self.db.find_by_location(SOURCE_LOCAL, r["location"]) for r in rows) if t]
        if ids:
            self.refresh_library()
            self.queue.set_context(ids, ids[0])
            self._start(ids[0])
