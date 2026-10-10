"""The favourites drawer on the right: every song marked as favourite, as cards. Double-click plays one."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu,
                               QStyle, QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget)

from ...db.database import Track
from ...i18n import tr, trn
from .. import icons, styles
from .queue_panel import play_time

ARTIST_ROLE = Qt.UserRole + 1
CARD_HEIGHT = 56


class _CardDelegate(QStyledItemDelegate):
    """A song as a card (title over artist), painted rather than built from widgets because the list can be long."""

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(0, CARD_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        card = QRectF(option.rect).adjusted(0, 3, 0, -3)
        selected, hot = bool(option.state & QStyle.State_Selected), bool(option.state & QStyle.State_MouseOver)
        accent = QColor(styles.RED)                       # rose, so it reads apart from the queue
        painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 62) if selected else QColor(styles.card_bg()))
        painter.setPen(QPen(accent if selected else (QColor(accent.red(), accent.green(), accent.blue(), 140) if hot
                                                         else QColor(styles.BORDER)), 1))
        painter.drawRoundedRect(card, 10, 10)
        inner = card.adjusted(14, 7, -12, -7)
        title_font = QFont(option.font)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(styles.TEXT))
        metrics = painter.fontMetrics()
        painter.drawText(QRectF(inner.left(), inner.top(), inner.width(), metrics.height()), Qt.AlignLeft | Qt.AlignVCenter,
                         metrics.elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight, int(inner.width())))
        small = QFont(option.font)
        small.setPixelSize(12)
        painter.setFont(small)
        painter.setPen(QColor(styles.SUBTEXT))
        metrics = painter.fontMetrics()
        painter.drawText(QRectF(inner.left(), inner.bottom() - metrics.height(), inner.width(), metrics.height()),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         metrics.elidedText(index.data(ARTIST_ROLE) or "", Qt.ElideRight, int(inner.width())))
        painter.restore()


class FavoritesPanel(QWidget):
    closed = Signal()
    play_requested = Signal(int)              # track id
    unfavorite_requested = Signal(list)       # track ids

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("favoritesPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._ids: list[int] = []

        self.heart = QLabel()
        self.heart.setFixedSize(20, 20)
        self.heading = QLabel()
        self.heading.setObjectName("heading")
        self.close_button = QToolButton()
        self.close_button.setObjectName("menuButton")
        self.close_button.setFixedSize(32, 32)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.clicked.connect(self.closed.emit)
        head = QHBoxLayout()
        head.setContentsMargins(16, 14, 10, 6)
        head.setSpacing(8)
        head.addWidget(self.heart)
        head.addWidget(self.heading, 1)
        head.addWidget(self.close_button)

        self.summary = QLabel()
        self.summary.setObjectName("queueTotal")
        self.summary.setContentsMargins(16, 0, 16, 6)
        self.empty = QLabel()
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)
        self.empty.setContentsMargins(16, 0, 16, 8)
        self.list = QListWidget()
        self.list.setObjectName("queueList")
        self.list.setItemDelegate(_CardDelegate(self.list))
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setMouseTracking(True)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemDoubleClicked.connect(lambda item: self.play_requested.emit(item.data(Qt.UserRole)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(head)
        layout.addWidget(self.summary)
        layout.addWidget(self.empty)
        layout.addWidget(self.list, 1)
        self.retranslate()
        self.apply_theme()
        styles.signals.changed.connect(lambda _n: self.apply_theme())

    def retranslate(self) -> None:
        self.heading.setText(tr("favorites.title"))
        self.close_button.setToolTip(tr("queue.hide"))
        self.empty.setText(tr("favorites.empty_hint"))

    def apply_theme(self) -> None:
        self.close_button.setIcon(icons.icon("close", styles.TEXT, size=18))
        self.heart.setPixmap(icons.icon("heart", styles.RED, size=18).pixmap(18, 18))
        self.list.viewport().update()

    def set_tracks(self, tracks: list[Track]) -> None:
        scroll = self.list.verticalScrollBar().value()
        keep = {self.list.item(self.list.row(i)).data(Qt.UserRole) for i in self.list.selectedItems()}
        self._ids = [t.id for t in tracks]
        self.list.setUpdatesEnabled(False)
        self.list.clear()
        for track in tracks:
            item = QListWidgetItem(track.title or tr("unknown_title"))
            item.setData(ARTIST_ROLE, track.artist or tr("unknown_artist"))
            item.setData(Qt.UserRole, track.id)
            self.list.addItem(item)
            if track.id in keep:
                item.setSelected(True)
        self.list.setUpdatesEnabled(True)
        self.list.verticalScrollBar().setValue(scroll)
        seconds = sum(t.duration for t in tracks if t.duration > 0)
        self.summary.setText(f"{trn('queue.count', len(tracks))} · {play_time(seconds)}" if tracks else "")
        self.empty.setVisible(not tracks)

    def _menu(self, pos) -> None:
        ids = [i.data(Qt.UserRole) for i in self.list.selectedItems()]
        if not ids:
            return
        menu = QMenu(self)
        if len(ids) == 1:
            menu.addAction(tr("menu.play"), lambda: self.play_requested.emit(ids[0]))
            menu.addSeparator()
        menu.addAction(tr("menu.unfavorite"), lambda: self.unfavorite_requested.emit(ids))
        menu.exec(self.list.viewport().mapToGlobal(pos))
