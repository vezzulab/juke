"""The queue column on the right: what is playing and the songs the person lined up (drag them to reorder)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from ...db.database import Track
from ...i18n import tr, trn
from .. import icons, styles
from .widgets import ElidedLabel


def play_time(seconds: float) -> str:
    """How long the songs play: seconds under a minute, minutes, then hours and minutes."""
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min" if minutes else f"{total} s"


def _line(track: Track | None) -> str:
    if track is None:
        return tr("queue.gone")
    return f"{track.title or tr('unknown_title')}\n{track.artist or tr('unknown_artist')}"


class _QueueList(QListWidget):
    """The songs the person lined up; dragging one to another place reorders them.
    A drop reports (from row, to row) and the owner redraws the list; Qt never moves the items by itself."""

    moved = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.queued = 0                                  # how many rows at the top are the person's queue
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        source = self.currentRow()
        if 0 <= source < self.queued:
            over = self.indexAt(event.position().toPoint())
            row = over.row() if over.isValid() else self.count()
            if over.isValid() and self.dropIndicatorPosition() == QAbstractItemView.BelowItem:
                row += 1
            target = min(row - 1 if row > source else row, self.queued - 1)      # last place is the end of the queue
            if target != source:
                self.moved.emit(source, max(0, target))
        event.ignore()


class QueuePanel(QWidget):
    closed = Signal()
    moved = Signal(int, int)                 # row in the queue, row it was dropped on
    remove_requested = Signal(list)          # rows
    play_requested = Signal(int)             # row: play this one now
    clear_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("queuePanel")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.heading = QLabel()
        self.heading.setObjectName("heading")
        self.clear_button = QPushButton()
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self.clear_requested.emit)
        self.close_button = QToolButton()
        self.close_button.setObjectName("menuButton")
        self.close_button.setFixedSize(32, 32)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.clicked.connect(self.closed.emit)
        head = QHBoxLayout()
        head.setContentsMargins(16, 14, 10, 6)
        head.setSpacing(6)
        head.addWidget(self.heading, 1)
        head.addWidget(self.clear_button)
        head.addWidget(self.close_button)

        self.now_label = self._section()
        self.now = QLabel()
        self.now.setObjectName("queueNow")
        self.now.setContentsMargins(16, 0, 16, 6)
        self.now.setWordWrap(True)
        self.next_label = self._section()
        self.summary = QLabel()                          # how many songs and how long they play
        self.summary.setObjectName("queueTotal")
        self.summary.setContentsMargins(16, 0, 16, 6)
        self.empty = QLabel()
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)
        self.empty.setContentsMargins(16, 0, 16, 8)
        self.queue_list = _QueueList()
        self.queue_list.setObjectName("queueList")
        self.queue_list.moved.connect(self.moved.emit)
        self.queue_list.itemDoubleClicked.connect(self._double_clicked)
        self.queue_list.customContextMenuRequested.connect(self._menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(head)
        layout.addWidget(self.now_label)
        layout.addWidget(self.now)
        layout.addWidget(self._rule())
        layout.addWidget(self.next_label)
        layout.addWidget(self.summary)
        layout.addWidget(self.empty)
        layout.addWidget(self.queue_list, 1)
        self.setMinimumWidth(260)
        self.retranslate()
        self.apply_theme()
        styles.signals.changed.connect(lambda _n: self.apply_theme())

    @staticmethod
    def _rule() -> QFrame:
        """A thin line between what is playing and the queue."""
        line = QFrame()
        line.setObjectName("queueRule")
        line.setFixedHeight(1)
        holder = QWidget()
        box = QVBoxLayout(holder)
        box.setContentsMargins(16, 8, 16, 4)
        box.addWidget(line)
        return holder

    @staticmethod
    def _section() -> QLabel:
        label = QLabel()
        label.setObjectName("queueSection")
        return label

    def retranslate(self) -> None:
        self.heading.setText(tr("queue.title"))
        self.clear_button.setText(tr("queue.clear"))
        self.close_button.setToolTip(tr("queue.hide"))
        self.now_label.setText(tr("queue.now").upper())
        self.next_label.setText(tr("queue.next").upper())
        self.empty.setText(tr("queue.empty_hint"))

    def apply_theme(self) -> None:
        self.close_button.setIcon(icons.icon("close", styles.TEXT, size=18))

    # -- content -------------------------------------------------------------------------------------------
    def set_content(self, current: Track | None, queued: list[Track | None]) -> None:
        """``queued``: the songs the person chose, in order (None for a song that is gone). Nothing else is listed:
        the rest of the playing list is not part of the queue."""
        self.now.setText(_line(current).replace("\n", " — ") if current is not None else tr("queue.nothing"))
        scroll = self.queue_list.verticalScrollBar().value()
        selected = {self.queue_list.row(i) for i in self.queue_list.selectedItems()}
        widget = self.queue_list
        widget.clear()
        widget.queued = len(queued)
        for track in queued:
            self._add(track)
        for row in selected:
            if row < len(queued):
                widget.item(row).setSelected(True)
        widget.verticalScrollBar().setValue(scroll)
        self.empty.setVisible(not queued)
        self.clear_button.setEnabled(bool(queued))
        seconds = sum(t.duration for t in queued if t is not None and t.duration > 0)
        self.summary.setText(f"{trn('queue.count', len(queued))} · {play_time(seconds)}" if queued else "")

    def _add(self, track: Track | None) -> None:
        """Each song is a card (the look comes from the stylesheet, so it follows the theme): title in the text colour,
        artist softer."""
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 56))
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
        self.queue_list.addItem(item)
        title, _, artist = _line(track).partition("\n")
        holder = QWidget()
        holder.setAttribute(Qt.WA_TransparentForMouseEvents, True)      # clicks and drags reach the list
        holder.setAttribute(Qt.WA_TranslucentBackground, True)
        box = QVBoxLayout(holder)
        box.setContentsMargins(12, 6, 12, 6)
        box.setSpacing(0)
        name = ElidedLabel(title)
        name.setObjectName("queueTitle")
        by = ElidedLabel(artist)
        by.setObjectName("queueArtist")
        box.addWidget(name)
        box.addWidget(by)
        self.queue_list.setItemWidget(item, holder)

    def _double_clicked(self, item: QListWidgetItem) -> None:
        row = self.queue_list.row(item)
        if row < self.queue_list.queued:
            self.play_requested.emit(row)

    def _menu(self, pos) -> None:
        rows = sorted(r for r in {self.queue_list.row(i) for i in self.queue_list.selectedItems()} if r < self.queue_list.queued)
        if not rows:
            return
        menu = QMenu(self)
        if len(rows) == 1:
            menu.addAction(tr("queue.play_now"), lambda: self.play_requested.emit(rows[0]))
            up = menu.addAction(tr("queue.move_up"), lambda: self.moved.emit(rows[0], rows[0] - 1))
            up.setEnabled(rows[0] > 0)
            down = menu.addAction(tr("queue.move_down"), lambda: self.moved.emit(rows[0], rows[0] + 1))
            down.setEnabled(rows[0] < self.queue_list.queued - 1)
            menu.addSeparator()
        menu.addAction(tr("menu.remove_from_queue"), lambda: self.remove_requested.emit(rows))
        menu.exec(self.queue_list.viewport().mapToGlobal(pos))


class QueueTab(QAbstractButton):
    """A folder tab on the queue's edge: its text reads upwards, a click slides the queue out or back. Open, it is the
    same colour as the queue and joins it with curves, as if the panel were a folder and this its tab; shut, it is a
    small handle on the window's edge."""

    WIDTH = 28
    FLARE = 9                                    # the curve with which the tab joins the panel

    def __init__(self, title_key: str = "queue.title", tip_key: str = "queue.tab_tip", favorites: bool = False,
                 parent=None) -> None:
        super().__init__(parent)
        self._title_key, self._tip_key = title_key, tip_key
        self._favorites = favorites               # the favourites tab wears rose, the queue's wears the accent
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._count = 0
        self.setFixedWidth(self.WIDTH)
        self.retranslate()

    def set_count(self, count: int) -> None:
        if count != self._count:
            self._count = count
            self.retranslate()

    def retranslate(self) -> None:
        self._label = tr(self._title_key).upper() + (f"  {self._count}" if self._count else "")
        body = int(self.fontMetrics().horizontalAdvance(self._label) * 1.35) + 30
        self.setFixedHeight(body + 2 * self.FLARE)
        self.setToolTip(tr(self._tip_key))
        self.update()

    def _shape(self, joined: bool) -> QPainterPath:
        w, h, f, r = float(self.width()), float(self.height()), float(self.FLARE), 10.0
        top, bottom = f, h - f
        path = QPainterPath()
        if joined:
            path.moveTo(w, 0)
            path.quadTo(w, top, w - f, top)                      # the curve out of the panel's edge
            path.lineTo(r, top)
            path.quadTo(0, top, 0, top + r)
            path.lineTo(0, bottom - r)
            path.quadTo(0, bottom, r, bottom)
            path.lineTo(w - f, bottom)
            path.quadTo(w, bottom, w, h)
            path.closeSubpath()
        else:
            path.moveTo(w + 4, top)
            path.lineTo(r, top)
            path.quadTo(0, top, 0, top + r)
            path.lineTo(0, bottom - r)
            path.quadTo(0, bottom, r, bottom)
            path.lineTo(w + 4, bottom)
            path.closeSubpath()
        return path

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setClipRect(QRectF(self.rect()))
        on, hot = self.isChecked(), self.underMouse()
        accent = QColor(styles.RED if self._favorites else styles.ACCENT)
        if on:                                               # the drawer's own colour: tab and panel are one piece
            painter.setBrush(QColor(styles.favorites_bg() if self._favorites else styles.queue_bg()))
            painter.setPen(Qt.NoPen)
            painter.drawPath(self._shape(True))
            painter.setPen(QPen(QColor(styles.BORDER), 1))
            painter.setBrush(Qt.NoBrush)
            path = self._shape(True)
            painter.drawPath(path)
        else:
            painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 64 if hot else 32))
            painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 190 if hot else 110), 1.2))
            painter.drawPath(self._shape(False))
        painter.setPen(accent if on or not hot else QColor(styles.TEXT))
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.3)
        painter.setFont(font)
        painter.translate(0, self.height())
        painter.rotate(-90)                                  # the text reads from bottom to top
        painter.drawText(QRectF(0, 0, self.height(), self.width() - (self.FLARE if on else 2)), Qt.AlignCenter, self._label)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)


class QueueDock(QWidget):
    """The tabs and the open drawer side by side, at the window's right edge. A panel keeps its full width and is only
    revealed as the dock grows, so sliding it out never reflows what is inside: the tabs come out with it."""

    PANEL_WIDTH = 320
    TAB_GAP = 8

    def __init__(self, drawers: list[tuple[QueueTab, QWidget]], parent=None) -> None:
        super().__init__(parent)
        self.drawers = drawers
        for tab, panel in drawers:
            tab.setParent(self)
            panel.setParent(self)
            panel.setMinimumWidth(0)
            panel.setFixedWidth(self.PANEL_WIDTH)
        self.setMinimumWidth(QueueTab.WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    def sizeHint(self) -> QSize:
        return QSize(QueueTab.WIDTH + self.PANEL_WIDTH, 100)

    def minimumSizeHint(self) -> QSize:
        return QSize(QueueTab.WIDTH, 0)

    def place(self) -> None:
        """The tabs one under the other in the middle of the edge (their curved ends overlap a little)."""
        overlap = QueueTab.FLARE
        total = sum(t.height() for t, _ in self.drawers) - overlap * (len(self.drawers) - 1)
        y = max(0, (self.height() - total) // 2)
        for tab, panel in self.drawers:
            tab.move(0, y)
            y += tab.height() - overlap + self.TAB_GAP
            panel.setGeometry(QueueTab.WIDTH, 0, self.PANEL_WIDTH, self.height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.place()
        super().resizeEvent(event)


class OverlayHost(QWidget):
    """Holds the main content and the queue dock. While the dock slides it floats over the content (only the dock moves,
    so the song list is not laid out and repainted on every frame); when it has landed, the content is told how much
    room is left."""

    def __init__(self, content: QWidget, dock: QueueDock, parent=None) -> None:
        super().__init__(parent)
        self.content, self.dock = content, dock
        content.setParent(self)
        dock.setParent(self)
        self._shown = QueueTab.WIDTH            # how wide the dock looks right now
        self._reserved = QueueTab.WIDTH         # how much room the content leaves for it
        self._place()

    @property
    def shown(self) -> int:
        return self._shown

    def set_shown(self, width: int) -> None:
        width = int(width)
        if width != self._shown:
            self._shown = width
            self._place(content=False)

    def set_reserved(self, width: int) -> None:
        if width != self._reserved:
            self._reserved = width
            self._place()

    def _place(self, content: bool = True) -> None:
        w, h = self.width(), self.height()
        if content:
            self.content.setGeometry(0, 0, max(0, w - self._reserved), h)
        self.dock.setGeometry(w - self._shown, 0, self._shown, h)
        self.dock.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._place()
        super().resizeEvent(event)
