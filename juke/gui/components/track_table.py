"""Central song table backed by a lazy, virtual model.

The model keeps only an ordered list of track ids for the current view (50 000
ints cost well under a megabyte) and pulls full rows from SQLite one page at a
time, on demand, while the view paints — so opening, sorting or filtering a
huge library never materialises it in Python.
"""

from __future__ import annotations

from collections import OrderedDict

import json
import math

from PySide6.QtCore import (QAbstractTableModel, QItemSelectionModel, QMimeData, QModelIndex, QRect, QRectF, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QAction, QColor, QDrag, QFont, QFontMetrics, QFontMetricsF, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QPushButton, QTableView

from ...db.database import SOURCE_AIRSONIC, Database, Scope, Track
from ...db.folders import ordered
from ...i18n import tr, trn
from .. import icons, styles
from .sidebar import MIME_TRACKS
from .widgets import format_duration

BEAT_MS = 60             # frame time of the bars beside the playing song: about 16 frames a second, one small cell each
BEAT_SLOW_MS = 110       # on battery: about 9 a second, skipping frames so the speed of the motion stays the same
BEAT_FRAMES = 24         # the bars loop seamlessly over this many frames
BEAT_SIZE = 22
COLUMNS = ("title", "artist", "album", "duration", "genre", "bitrate", "source", "playlists")
IN_LISTS = COLUMNS.index("playlists")      # which playlists hold the song: shown everywhere except inside a playlist
NUMERIC = {"duration", "bitrate"}


class TrackModel(QAbstractTableModel):
    PAGE = 256
    MAX_PAGES = 48

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._ids: list[int] = []
        self._pages: OrderedDict[int, list[Track | None]] = OrderedDict()
        self._scope = Scope()
        self._fixed: list[int] | None = None
        self.availability = None                                 # juke.availability.Availability: which songs cannot play now
        self.lists_visible = False                               # the "in playlists" column is on screen: look the names up
        self._names: dict[int, list[str]] = {}                   # track id -> playlists holding it, for the pages loaded
        self._entries: dict[int, list[tuple[int, float]]] = {}   # playlist view: track id -> [(position, added at)] per copy
        self._row_entry: list[tuple[int, float]] = []            # parallel to _ids when _entries is in use
        self._text = ""
        self._sort: str | None = None
        self._descending = False
        self._current: int | None = None
        self._state = "stopped"                   # playing: speaker beside the song; paused: pause sign; stopped: nothing
        self._played: set[int] = set()            # songs started since Juke was opened: only in memory, gone when it closes
        self._marks: dict[str, object] = {}       # the pause icon and the bar frames, made the first time a row needs them
        self._frame = 0
        self._animating = False                   # the window is in front and the user allows motion (as for the level meter)
        self._beat = QTimer(self)
        self._beat.setTimerType(Qt.PreciseTimer)       # even frames: a coarse timer batches wake-ups and the motion stutters
        self._beat.setInterval(BEAT_MS)
        self._beat_step = 1
        self._frames_cache: list[QPixmap] = []
        self._beat.timeout.connect(self._tick)
        self._current_font = QFont()
        self._current_font.setBold(True)
        self._accent = QColor(styles.ACCENT)
        self._muted = QColor(styles.SUBTEXT)
        self._dim = QColor(styles.MUTED)

    def apply_theme(self) -> None:
        self._accent, self._muted = QColor(styles.ACCENT), QColor(styles.SUBTEXT)
        self._dim = QColor(styles.MUTED)
        self._marks.clear()
        self._frames_cache = []
        self.invalidate_rows()

    # -- view definition --------------------------------------------------------------------
    def set_view(self, scope: Scope = Scope(), fixed_ids: list[int] | None = None,
                 sort: str | None = None, descending: bool = False,
                 entries: list[tuple[int, int, float]] | None = None) -> None:
        self._scope, self._fixed = scope, fixed_ids
        self._sort, self._descending = sort, descending
        self._index_entries(entries)
        self.reload(force=True)                       # another view: the table starts afresh

    def set_text(self, text: str) -> None:
        if text != self._text:
            self._text = text
            self.reload()

    def set_sort(self, key: str | None, descending: bool = False) -> None:
        self._sort, self._descending = key, descending
        self.reload()

    def set_fixed_ids(self, ids: list[int]) -> None:
        self._fixed = ids
        self.reload()

    def set_entries(self, entries: list[tuple[int, int, float]] | None) -> None:
        """Playlist view: (track id, position, added at) of every entry. A song added twice is two rows, each with its
        own position and date, so one of them can be removed without touching the other."""
        self._index_entries(entries)
        self._fixed = [e[0] for e in entries] if entries is not None else None
        self.reload()

    def _index_entries(self, entries: list[tuple[int, int, float]] | None) -> None:
        self._entries = {}
        for track_id, position, added in entries or []:
            self._entries.setdefault(track_id, []).append((position, added))

    def entry_positions(self, rows: list[int]) -> list[int]:
        """Playlist positions behind these rows."""
        return [self._row_entry[r][0] for r in rows if 0 <= r < len(self._row_entry)]

    def reload(self, force: bool = False) -> None:
        ids = self._compute_ids()
        if ids == self._ids and self._ids and not force:
            # Same songs in the same order (a rescan that found nothing, a favourite toggled): no reset, so the view
            # keeps its place and nothing is repainted beyond the rows that may have changed.
            self._row_entry = self._match_entries(ids)
            self.invalidate_rows()
            return
        self.beginResetModel()
        self._ids = ids
        self._row_entry = self._match_entries(ids)
        self._pages.clear()
        self._names.clear()
        self.endResetModel()

    def _match_entries(self, ids: list[int]) -> list[tuple[int, float]]:
        """The playlist entry behind each row: the n-th row of a song takes that song's n-th entry."""
        if not self._entries:
            return []
        seen: dict[int, int] = {}
        rows = []
        for track_id in ids:
            n = seen.get(track_id, 0)
            seen[track_id] = n + 1
            copies = self._entries.get(track_id, [])
            rows.append(copies[n] if n < len(copies) else (-1, 0.0))
        return rows

    def _compute_ids(self) -> list[int]:
        if self._fixed is None:
            return self._db.query_ids(self._scope, self._text, self._sort, self._descending)
        if self._sort is None and not self._text:
            return list(self._fixed)
        ordered = self._db.query_ids(Scope(), self._text, self._sort, self._descending)
        if self._sort is None:  # keep the queue order, just filter
            keep = set(ordered)
            return [i for i in self._fixed if i in keep]
        copies = {}
        for i in self._fixed:                                  # a song that is in the list twice shows twice
            copies[i] = copies.get(i, 0) + 1
        return [i for i in ordered for _ in range(copies.get(i, 0))]

    def mark_played(self, track_id: int) -> None:
        """This song has started playing: it keeps a check mark until Juke is closed."""
        if track_id in self._played:
            return
        self._played.add(track_id)
        for row, wanted in enumerate(self._ids):
            if wanted == track_id:
                self.dataChanged.emit(self.index(row, 0), self.index(row, 0), [Qt.DecorationRole])

    def repaint_rows(self) -> None:
        """Which songs can be played changed: repaint, without asking the database again."""
        if self._ids:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._ids) - 1, len(COLUMNS) - 1))

    def invalidate_rows(self) -> None:
        """Rows changed in the database (favourite, tags, playlists): drop cached pages and repaint."""
        self._pages.clear()
        self._names.clear()
        if self._ids:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._ids) - 1, len(COLUMNS) - 1))

    # -- access -----------------------------------------------------------------------------------
    def ids(self) -> list[int]:
        return list(self._ids)

    def id_at(self, row: int) -> int | None:
        return self._ids[row] if 0 <= row < len(self._ids) else None

    def track_at(self, row: int) -> Track | None:
        if not 0 <= row < len(self._ids):
            return None
        page_no, offset = divmod(row, self.PAGE)
        page = self._pages.get(page_no)
        if page is None:
            wanted = self._ids[page_no * self.PAGE:(page_no + 1) * self.PAGE]
            by_id = {t.id: t for t in self._db.tracks_by_ids(wanted)}
            page = [by_id.get(i) for i in wanted]
            if self.lists_visible:
                self._names.update(self._db.playlist_names(wanted))
            if self.availability is not None:
                self.availability.want(page)             # (in the background) are the files of these rows there?
            self._pages[page_no] = page
            while len(self._pages) > self.MAX_PAGES:
                self._pages.popitem(last=False)
        else:
            self._pages.move_to_end(page_no)
        return page[offset]

    def playlist_coverage(self, ids: list[int]) -> dict[int, int]:
        return self._db.playlist_coverage(ids)

    @staticmethod
    def _badge_colors() -> tuple[QColor, QColor]:
        """A badge in the theme's second accent (not the colour of the playing row's text) and bars that read on it."""
        fill = QColor(styles.ACCENT2)
        luma = 0.299 * fill.red() + 0.587 * fill.green() + 0.114 * fill.blue()
        return fill, QColor("#10131a") if luma > 150 else QColor("#ffffff")

    def _draw_mark(self, bars: list[float] | None) -> QPixmap:
        """The badge with equalizer bars of the given heights (0..1), or a pause sign when ``bars`` is None."""
        screen = QGuiApplication.primaryScreen()
        ratio = max(1.0, screen.devicePixelRatio()) if screen else 1.0
        size = BEAT_SIZE
        pixmap = QPixmap(int(size * ratio), int(size * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)
        fill, ink = self._badge_colors()
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), 6, 6)
        painter.setBrush(ink)
        inner = size - 8.0
        if bars is None:
            for x in (7.0, 12.0):
                painter.drawRoundedRect(QRectF(x, 6.5, 3.0, size - 13.0), 1.2, 1.2)
        else:
            for i, level in enumerate(bars):
                height = max(2.0, inner * level)
                painter.drawRoundedRect(QRectF(4.5 + i * 3.6, size - 4.0 - height, 2.6, height), 1.2, 1.2)
        painter.end()
        return pixmap

    def _frames(self) -> list[QPixmap]:
        """The bars, drawn once per theme: four that rise and fall out of step, looping without a seam."""
        if not self._frames_cache:
            for k in range(BEAT_FRAMES):
                self._frames_cache.append(self._draw_mark([
                    0.22 + 0.78 * abs(math.sin(math.pi * (turns * k / BEAT_FRAMES + phase)))
                    for turns, phase in ((1, 0.0), (2, 0.31), (1, 0.62), (3, 0.12))]))
        return self._frames_cache

    def _mark(self):
        if self._state == "paused":
            if "pause" not in self._marks:
                self._marks["pause"] = self._draw_mark(None)
            return self._marks["pause"]
        return self._frames()[self._frame if self._animating else BEAT_FRAMES // 3]

    def set_animating(self, allowed: bool, slow: bool = False) -> None:
        """Bars move only while the song plays and the window is in front. They are one small cell, so unlike the
        big level meter they also move on battery, just slower."""
        self._animating = bool(allowed)
        self._beat.setInterval(BEAT_SLOW_MS if slow else BEAT_MS)
        self._beat_step = 2 if slow else 1
        self._beat.setTimerType(Qt.CoarseTimer if slow else Qt.PreciseTimer)
        self._sync_beat()

    def _sync_beat(self) -> None:
        if self._animating and self._state == "playing" and self._current is not None:
            if not self._beat.isActive():
                self._beat.start()
        else:
            self._beat.stop()                       # nothing moves: no wake-ups at all

    def _tick(self) -> None:
        self._frame = (self._frame + self._beat_step) % BEAT_FRAMES
        self._repaint_current()

    def set_state(self, state: str) -> None:
        """Bars while it plays, pause sign while it is paused, nothing once stopped: only that row is repainted."""
        if state != self._state:
            self._state = state
            self._sync_beat()
            self._repaint_current()

    def _repaint_current(self) -> None:
        if self._current is None:
            return
        try:
            row = self._ids.index(self._current)
        except ValueError:
            return
        self.dataChanged.emit(self.index(row, 0), self.index(row, 0), [Qt.DecorationRole])

    def set_current(self, track_id: int | None) -> None:
        previous, self._current = self._current, track_id
        self._sync_beat()
        for wanted in (previous, track_id):
            if wanted is None:
                continue
            try:
                row = self._ids.index(wanted)
            except ValueError:
                continue
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))

    # -- Qt model interface ------------------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._ids)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal or not 0 <= section < len(COLUMNS):
            return None
        if role == Qt.DisplayRole:
            return tr("col." + COLUMNS[section])
        if role == Qt.TextAlignmentRole and COLUMNS[section] in NUMERIC:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def refresh_headers(self) -> None:
        self.headerDataChanged.emit(Qt.Horizontal, 0, len(COLUMNS) - 1)

    def flags(self, index: QModelIndex):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def mimeTypes(self) -> list[str]:  # noqa: N802
        return [MIME_TRACKS]

    def mimeData(self, indexes) -> QMimeData:  # noqa: N802
        """The dragged songs as a list of ids: a playlist or a folder of the sidebar takes them."""
        rows = sorted({i.row() for i in indexes})
        ids = [i for i in (self.id_at(r) for r in rows) if i is not None]
        mime = QMimeData()
        mime.setData(MIME_TRACKS, json.dumps(ids).encode())
        return mime

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        column = COLUMNS[index.column()]
        if role == Qt.TextAlignmentRole:
            return int((Qt.AlignRight if column in NUMERIC else Qt.AlignLeft) | Qt.AlignVCenter)
        if role not in (Qt.DisplayRole, Qt.FontRole, Qt.ForegroundRole, Qt.ToolTipRole, Qt.DecorationRole):
            return None
        if role == Qt.DecorationRole:                 # beside the title: the bars of what is on, a check for what played
            if column != "title":
                return None
            track_id = self.id_at(index.row())
            if track_id is not None and track_id == self._current and self._current is not None and self._state != "stopped":
                return self._mark()
            if track_id in self._played:                  # played since Juke was opened (not kept for the next time)
                if "played" not in self._marks:
                    self._marks["played"] = icons.icon("check", styles.GREEN, size=15)
                return self._marks["played"]
            return None
        track = self.track_at(index.row())
        if track is None:
            return None
        playing = track.id == self._current
        why = self.availability.reason(track) if self.availability is not None else None   # "server" | "file" | None
        if role == Qt.FontRole:
            return self._current_font if playing else None
        if role == Qt.ForegroundRole:
            if why:
                return self._dim                      # cannot be played now: grey
            if playing:
                return self._accent
            return self._muted if column not in ("title", "artist") else None
        if role == Qt.ToolTipRole:
            if why:
                return tr("avail.tip_server" if why == "server" else "avail.tip_file")
            if column == "playlists":
                return "\n".join(self._names.get(track.id, ())) or None
            return f"{track.title}\n{track.artist} — {track.album}" if column == "title" else None
        if column == "title":
            return ("★ " if track.favorite else "") + (track.title or tr("unknown_title"))
        if column == "artist":
            return track.artist or tr("unknown_artist")
        if column == "album":
            return track.album or tr("unknown_album")
        if column == "duration":
            return format_duration(track.duration)
        if column == "genre":
            return track.genre
        if column == "bitrate":
            return f"{track.bitrate} kbps" if track.bitrate else ""
        if column == "playlists":
            return ", ".join(self._names.get(track.id, ()))
        if why:                                       # the note where the source is: what to do about it
            return tr("avail.go_online" if why == "server" else "avail.not_connected")
        return "Airsonic" if track.source_type == SOURCE_AIRSONIC else tr("source.local")


class TrackTable(QTableView):
    play_requested = Signal(int)                 # track id (double click / Enter)
    play_next_requested = Signal(list)
    queue_requested = Signal(list)
    favorite_requested = Signal(list, bool)
    edit_requested = Signal(list)
    lyrics_requested = Signal(int)        # add or edit the lyrics of one song
    find_lyrics_requested = Signal(int)   # search for them online
    remove_from_queue_requested = Signal(list)
    add_to_playlist_requested = Signal(int, list)   # playlist id, track ids
    new_playlist_requested = Signal(list)           # create a playlist holding these tracks
    remove_songs_from_playlist_requested = Signal(int, list)   # playlist id, track ids: the ✓ of the menu pressed again
    remove_from_playlist_requested = Signal(list)   # playlist positions, one per copy to take out
    add_to_folder_requested = Signal(int, list)     # folder id, track ids
    new_folder_requested = Signal(list)             # create a folder holding these tracks
    remove_from_folder_requested = Signal(list)
    send_to_device_requested = Signal(str, list)    # device key, track ids
    action_requested = Signal()                     # the button of an empty-state message

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.track_model = TrackModel(db, self)
        self.setModel(self.track_model)
        self.queue_mode = False
        self.playlist_mode = False
        self.folder_mode = False                    # showing one of the user's folders: songs can be taken out of it
        self.duplicate_mode: str | None = None      # showing copies of songs ("same" | "exact")
        self.playlists: list[tuple[int, str]] = []
        self.devices: list[tuple[str, str]] = []        # (key, name) of the phones that are ready to take songs
        self._folder_children: dict[int | None, list] = {}
        self.empty_title = ""
        self.empty_hint = ""
        self.empty_action = ""
        self.empty_button = QPushButton(self.viewport())
        self.empty_button.setObjectName("primary")
        self.empty_button.setCursor(Qt.PointingHandCursor)
        self.empty_button.clicked.connect(self.action_requested)
        self.empty_button.hide()
        self.track_model.modelReset.connect(self._place_empty_button)
        self._fresh_view = False                    # the next reset is another view: start at the top
        self._kept: tuple[int, list[int], int | None] | None = None
        self.track_model.modelAboutToBeReset.connect(self._remember_place)
        self.track_model.modelReset.connect(self._restore_place)
        self._sort_column = -1
        self._sort_desc = False

        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(36)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(-1, Qt.AscendingOrder)
        header.setMinimumSectionSize(60)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for column in (0, 1, 2):
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        for column, width in ((3, 84), (4, 130), (5, 100), (6, 96), (7, 170)):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            self.setColumnWidth(column, width)
        header.sectionClicked.connect(self._header_clicked)
        self.doubleClicked.connect(lambda index: self._emit_play(index.row()))

    # -- sorting ----------------------------------------------------------------------------------
    def _header_clicked(self, column: int) -> None:
        if COLUMNS[column] == "playlists":                    # a list of names, not something to sort by
            return
        # asc -> desc -> back to the view's natural order
        if column == self._sort_column and not self._sort_desc:
            self._sort_desc = True
        elif column == self._sort_column:
            self._sort_column, self._sort_desc = -1, False
        else:
            self._sort_column, self._sort_desc = column, False
        order = Qt.DescendingOrder if self._sort_desc else Qt.AscendingOrder
        self.horizontalHeader().setSortIndicator(self._sort_column, order)
        key = COLUMNS[self._sort_column] if self._sort_column >= 0 else None
        self.track_model.set_sort(key, self._sort_desc)

    def show_view(self, scope: Scope = Scope(), fixed_ids: list[int] | None = None, sort: str | None = None,
                  entries: list[tuple[int, int, float]] | None = None) -> None:
        """Switch to another slice of the library, resetting the header sort indicator."""
        self._sort_column = COLUMNS.index(sort) if sort else -1
        self._sort_desc = False
        self.horizontalHeader().setSortIndicator(self._sort_column, Qt.AscendingOrder)
        self.setColumnHidden(IN_LISTS, self.playlist_mode)      # inside a playlist it is obvious which one holds the song
        self.track_model.lists_visible = not self.playlist_mode
        self._fresh_view = True
        self.track_model.set_view(scope, fixed_ids, sort, False, entries)

    def recheck_availability(self) -> None:
        """Look again (in the background) at the files of the rows on screen."""
        model = self.track_model
        if model.availability is None or not model.rowCount():
            return
        first = max(0, self.rowAt(0))
        last = self.rowAt(self.viewport().height() - 1)
        last = model.rowCount() - 1 if last < 0 else last
        model.availability.want([model.track_at(r) for r in range(first, last + 1)])

    def _remember_place(self) -> None:
        """The list is about to be rebuilt (a rescan, a favourite, the queue moving on): keep where the person was."""
        rows = sorted({i.row() for i in self.selectionModel().selectedRows()})
        current = self.currentIndex().row() if self.currentIndex().isValid() else -1
        self._kept = (self.verticalScrollBar().value(),
                      [i for i in (self.track_model.id_at(r) for r in rows) if i is not None],
                      self.track_model.id_at(current) if current >= 0 else None)

    def _restore_place(self) -> None:
        kept, self._kept = self._kept, None
        if self._fresh_view or kept is None:
            if self._fresh_view:
                self.verticalScrollBar().setValue(0)
            self._fresh_view = False
            return
        scroll, selected, current = kept
        model = self.track_model
        if selected or current is not None:
            wanted = set(selected)
            selection = self.selectionModel()
            selection.clearSelection()
            for row, track_id in enumerate(model._ids):              # one pass, no copies of the list
                if track_id in wanted:
                    selection.select(model.index(row, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
                if track_id == current:
                    selection.setCurrentIndex(model.index(row, 0), QItemSelectionModel.NoUpdate)
                    current = None
        self.verticalScrollBar().setValue(scroll)

    def show_playlist(self, entries: list[tuple[int, int, float]]) -> None:
        """Open a playlist: every entry is a row, with the date it was added."""
        self.show_view(Scope(), [e[0] for e in entries], entries=entries)

    def selected_entry_positions(self) -> list[int]:
        """Playlist positions of the selected rows (a song in the list twice has one position per copy)."""
        rows = sorted({i.row() for i in self.selectionModel().selectedRows()})
        return self.track_model.entry_positions(rows)

    def startDrag(self, supported_actions) -> None:  # noqa: N802
        ids = self.selected_ids()
        if not ids:
            return
        drag = QDrag(self)
        drag.setMimeData(self.track_model.mimeData(self.selectionModel().selectedRows()))
        label = trn("summary.songs", len(ids))
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setBold(True)
        width = QFontMetricsF(font).horizontalAdvance(label) + 30
        pixmap = QPixmap(int(width), 30)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(styles.qcolor(styles.ACCENT, 235))
        painter.drawRoundedRect(QRectF(0, 0, width, 30), 9, 9)
        painter.setFont(font)
        painter.setPen(QColor(styles.ON_ACCENT))
        painter.drawText(QRectF(0, 0, width, 30), Qt.AlignCenter, label)
        painter.end()
        drag.setPixmap(pixmap)
        drag.exec(Qt.CopyAction)

    # -- selection helpers -----------------------------------------------------------------------------
    def selected_ids(self) -> list[int]:
        rows = sorted({i.row() for i in self.selectionModel().selectedRows()})
        return [i for i in (self.track_model.id_at(r) for r in rows) if i is not None]

    def _emit_play(self, row: int) -> None:
        track_id = self.track_model.id_at(row)
        if track_id is not None:
            self.play_requested.emit(track_id)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.currentIndex().isValid():
            self._emit_play(self.currentIndex().row())
            return
        super().keyPressEvent(event)

    # -- context menu ------------------------------------------------------------------------------------
    def contextMenuEvent(self, event) -> None:  # noqa: N802
        index = self.indexAt(event.pos())
        if not index.isValid():
            return
        if not self.selectionModel().isRowSelected(index.row()):
            self.selectRow(index.row())
        ids = self.selected_ids()
        if not ids:
            return
        tracks = [t for t in (self.track_model.track_at(r) for r in sorted({i.row() for i in self.selectionModel().selectedRows()})) if t]
        menu = QMenu(self)
        play = menu.addAction(tr("menu.play"))
        play.triggered.connect(lambda: self._emit_play(index.row()))
        menu.addAction(tr("menu.play_next"), lambda: self.play_next_requested.emit(ids))
        menu.addAction(tr("menu.add_to_queue"), lambda: self.queue_requested.emit(ids))
        if self.queue_mode:
            menu.addAction(tr("menu.remove_from_queue"), lambda: self.remove_from_queue_requested.emit(ids))
        playlists = menu.addMenu(tr("menu.add_to_playlist"))
        coverage, wanted = self.track_model.playlist_coverage(ids), len(set(ids))
        for playlist_id, name in self.playlists:
            held = coverage.get(playlist_id, 0)
            if held >= wanted:           # every selected song is in it: ✓, and choosing it takes them out again
                playlists.addAction(f"✓  {name}", lambda _c=False, pid=playlist_id: self.remove_songs_from_playlist_requested.emit(pid, ids))
            else:                        # some or none: choosing it adds the ones that are missing
                label = f"◐  {name}" if held else name
                playlists.addAction(label, lambda _c=False, pid=playlist_id: self.add_to_playlist_requested.emit(pid, ids))
        if self.playlists:
            playlists.addSeparator()
        playlists.addAction(tr("menu.new_playlist"), lambda: self.new_playlist_requested.emit(ids))
        if self.playlist_mode:
            positions = self.selected_entry_positions()
            menu.addAction(tr("menu.remove_from_playlist"), lambda: self.remove_from_playlist_requested.emit(positions))
        self._add_folder_menu(menu, ids)
        if len(self.devices) == 1:
            key, name = self.devices[0]
            menu.addAction(tr("menu.send_to_device", name=name), lambda: self.send_to_device_requested.emit(key, ids))
        elif self.devices:
            send = menu.addMenu(tr("menu.send_to"))
            for key, name in self.devices:
                send.addAction(name, lambda _c=False, k=key: self.send_to_device_requested.emit(k, ids))
        if self.folder_mode:
            menu.addAction(tr("menu.remove_from_folder"), lambda: self.remove_from_folder_requested.emit(ids))
        menu.addSeparator()
        all_favorites = bool(tracks) and all(t.favorite for t in tracks)
        label = tr("menu.unfavorite") if all_favorites else tr("menu.favorite")
        menu.addAction(label, lambda: self.favorite_requested.emit(ids, not all_favorites))
        edit = QAction(tr("menu.edit_metadata"), menu)
        edit.setEnabled(any(t.is_local for t in tracks))
        edit.triggered.connect(lambda: self.edit_requested.emit(list(ids)))
        menu.addAction(edit)
        single = len(tracks) == 1
        add_lyrics = menu.addAction(tr("menu.lyrics"), lambda: self.lyrics_requested.emit(ids[0]))
        add_lyrics.setEnabled(single)
        find_lyrics = menu.addAction(tr("menu.find_lyrics"), lambda: self.find_lyrics_requested.emit(ids[0]))
        find_lyrics.setEnabled(single)
        menu.exec(event.globalPos())

    def set_folders(self, folders: list) -> None:
        self._folder_children = {}
        for folder in folders:
            self._folder_children.setdefault(folder.parent_id, []).append(folder)

    def _add_folder_menu(self, menu: QMenu, ids: list[int]) -> None:
        """"Add to Folder": the tree of folders as nested menus, each level built only when it is opened."""
        root = menu.addMenu(tr("menu.add_to_folder"))

        def fill(target: QMenu, parent_id: int | None) -> None:
            target.clear()
            if parent_id is not None:
                target.addAction(tr("menu.this_folder"), lambda _c=False, fid=parent_id: self.add_to_folder_requested.emit(fid, ids))
                target.addSeparator()
            for folder in ordered(self._folder_children.get(parent_id, []), "name"):
                if self._folder_children.get(folder.id):
                    sub = target.addMenu(folder.name)
                    sub.aboutToShow.connect(lambda m=sub, fid=folder.id: fill(m, fid))
                    sub.addAction("…")                    # so the entry opens; replaced when it does
                else:
                    target.addAction(folder.name, lambda _c=False, fid=folder.id: self.add_to_folder_requested.emit(fid, ids))
            if parent_id is None:
                if self._folder_children.get(None):
                    target.addSeparator()
                target.addAction(tr("menu.new_folder"), lambda: self.new_folder_requested.emit(ids))

        fill(root, None)

    # -- empty state ---------------------------------------------------------------------------------------
    def set_playlists(self, playlists: list[tuple[int, str]]) -> None:
        self.playlists = playlists

    def set_empty_text(self, title: str, hint: str = "", action: str = "") -> None:
        """Message shown over an empty table, with an optional button (``action_requested``)."""
        self.empty_title, self.empty_hint, self.empty_action = title, hint, action
        self.empty_button.setText(action)
        self._place_empty_button()
        self.viewport().update()

    def _place_empty_button(self) -> None:
        show = bool(self.empty_action) and self.track_model.rowCount() == 0 and bool(self.empty_title)
        self.empty_button.setVisible(show)
        if not show:
            return
        rect = self.viewport().rect()
        half = rect.height() // 2
        font = QFont(self.font())
        font.setPixelSize(13)
        hint_height = QFontMetrics(font).boundingRect(0, 0, max(200, rect.width() - 48), 400, int(Qt.TextWordWrap), self.empty_hint).height() if self.empty_hint else 0
        self.empty_button.adjustSize()
        width = self.empty_button.sizeHint().width() + 24
        self.empty_button.setFixedSize(width, 38)
        self.empty_button.move((rect.width() - width) // 2, half + 6 + hint_height + 18)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_empty_button()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.track_model.rowCount() or not self.empty_title:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.viewport().rect()
        half = rect.height() // 2
        font = QFont(self.font())
        font.setPixelSize(16)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(styles.TEXT))
        painter.drawText(QRect(24, 0, rect.width() - 48, half - 4), Qt.AlignHCenter | Qt.AlignBottom, self.empty_title)
        if self.empty_hint:
            font.setPixelSize(13)
            font.setWeight(QFont.Normal)
            painter.setFont(font)
            painter.setPen(QColor(styles.SUBTEXT))
            painter.drawText(QRect(24, half + 6, rect.width() - 48, half - 6),
                             Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, self.empty_hint)
