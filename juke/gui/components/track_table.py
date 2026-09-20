"""Central song table backed by a lazy, virtual model.

The model keeps only an ordered list of track ids for the current view (50 000
ints cost well under a megabyte) and pulls full rows from SQLite one page at a
time, on demand, while the view paints — so opening, sorting or filtering a
huge library never materialises it in Python.
"""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTableView

from ...db.database import SOURCE_AIRSONIC, Database, Scope, Track
from ...i18n import tr
from .. import styles
from .widgets import format_duration

COLUMNS = ("title", "artist", "album", "duration", "genre", "bitrate", "source")
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
        self._text = ""
        self._sort: str | None = None
        self._descending = False
        self._current: int | None = None
        self._current_font = QFont()
        self._current_font.setBold(True)
        self._accent = QColor(styles.ACCENT)
        self._muted = QColor(styles.SUBTEXT)

    # -- view definition --------------------------------------------------------------------
    def set_view(self, scope: Scope = Scope(), fixed_ids: list[int] | None = None,
                 sort: str | None = None, descending: bool = False) -> None:
        self._scope, self._fixed = scope, fixed_ids
        self._sort, self._descending = sort, descending
        self.reload()

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

    def reload(self) -> None:
        ids = self._compute_ids()
        self.beginResetModel()
        self._ids = ids
        self._pages.clear()
        self.endResetModel()

    def _compute_ids(self) -> list[int]:
        if self._fixed is None:
            return self._db.query_ids(self._scope, self._text, self._sort, self._descending)
        if self._sort is None and not self._text:
            return list(self._fixed)
        ordered = self._db.query_ids(Scope(), self._text, self._sort, self._descending)
        if self._sort is None:  # keep the queue order, just filter
            keep = set(ordered)
            return [i for i in self._fixed if i in keep]
        members = set(self._fixed)
        return [i for i in ordered if i in members]

    def invalidate_rows(self) -> None:
        """Rows changed in the database (favourite, tags): drop cached pages and repaint."""
        self._pages.clear()
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
            self._pages[page_no] = page
            while len(self._pages) > self.MAX_PAGES:
                self._pages.popitem(last=False)
        else:
            self._pages.move_to_end(page_no)
        return page[offset]

    def set_current(self, track_id: int | None) -> None:
        previous, self._current = self._current, track_id
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
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        column = COLUMNS[index.column()]
        if role == Qt.TextAlignmentRole:
            return int((Qt.AlignRight if column in NUMERIC else Qt.AlignLeft) | Qt.AlignVCenter)
        if role not in (Qt.DisplayRole, Qt.FontRole, Qt.ForegroundRole, Qt.ToolTipRole):
            return None
        track = self.track_at(index.row())
        if track is None:
            return None
        playing = track.id == self._current
        if role == Qt.FontRole:
            return self._current_font if playing else None
        if role == Qt.ForegroundRole:
            if playing:
                return self._accent
            return self._muted if column not in ("title", "artist") else None
        if role == Qt.ToolTipRole:
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
        return "Airsonic" if track.source_type == SOURCE_AIRSONIC else tr("source.local")


class TrackTable(QTableView):
    play_requested = Signal(int)                 # track id (double click / Enter)
    play_next_requested = Signal(list)
    queue_requested = Signal(list)
    favorite_requested = Signal(list, bool)
    edit_requested = Signal(int)
    remove_from_queue_requested = Signal(list)

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.track_model = TrackModel(db, self)
        self.setModel(self.track_model)
        self.queue_mode = False
        self.empty_title = ""
        self.empty_hint = ""
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
        for column, width in ((3, 84), (4, 130), (5, 100), (6, 96)):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            self.setColumnWidth(column, width)
        header.sectionClicked.connect(self._header_clicked)
        self.doubleClicked.connect(lambda index: self._emit_play(index.row()))

    # -- sorting ----------------------------------------------------------------------------------
    def _header_clicked(self, column: int) -> None:
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

    def show_view(self, scope: Scope = Scope(), fixed_ids: list[int] | None = None, sort: str | None = None) -> None:
        """Switch to another slice of the library, resetting the header sort indicator."""
        self._sort_column = COLUMNS.index(sort) if sort else -1
        self._sort_desc = False
        self.horizontalHeader().setSortIndicator(self._sort_column, Qt.AscendingOrder)
        self.track_model.set_view(scope, fixed_ids, sort, False)

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
        menu.addSeparator()
        all_favorites = bool(tracks) and all(t.favorite for t in tracks)
        label = tr("menu.unfavorite") if all_favorites else tr("menu.favorite")
        menu.addAction(label, lambda: self.favorite_requested.emit(ids, not all_favorites))
        edit = QAction(tr("menu.edit_metadata"), menu)
        edit.setEnabled(len(tracks) == 1 and tracks[0].is_local)
        edit.triggered.connect(lambda: self.edit_requested.emit(ids[0]))
        menu.addAction(edit)
        menu.exec(event.globalPos())

    # -- empty state ---------------------------------------------------------------------------------------
    def set_empty_text(self, title: str, hint: str = "") -> None:
        self.empty_title, self.empty_hint = title, hint
        self.viewport().update()

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
