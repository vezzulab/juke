"""Internet radio: "My Stations" (saved in the database) and "Explore Radio" (Radio-Browser search)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QFrame, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QProgressBar, QPushButton, QStackedLayout, QToolButton, QVBoxLayout,
                               QWidget)

from ...api import radio
from ...db.database import Database, Station, normalize
from ...i18n import tr, trn
from ...workers import AsyncWorker
from .. import icons, styles
from .widgets import ElidedLabel

CHIPS = ("salsa", "bachata", "merengue", "latin", "pop", "rock", "jazz", "electronic", "classical", "news")
ROW_HEIGHT = 70
ICON = 46


def station_pixmap(station: Station, size: int = ICON) -> QPixmap:
    """The station's cached icon, or a neutral radio glyph."""
    if station.favicon:
        path = radio.icon_path(station.favicon)
        if path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                dpr = pixmap.devicePixelRatioF() or 1.0
                return pixmap.scaled(int(size * 2), int(size * 2), Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return icons.glyph("radio", styles.SUBTEXT, 24)


class StationRow(QFrame):
    play_clicked = Signal()
    action_clicked = Signal()

    def __init__(self, station: Station, mode: str, saved: bool, parent=None) -> None:
        super().__init__(parent)
        self.station, self.mode, self._saved = station, mode, saved
        self.setObjectName("stationRow")
        self.setProperty("playing", False)
        self.setFixedHeight(ROW_HEIGHT - 6)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("stationIcon")
        self.icon_label.setFixedSize(ICON, ICON)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setScaledContents(False)
        name = ElidedLabel(station.name)
        name.setObjectName("stationName")
        parts = [station.tags.split(",")[0].strip() if station.tags else "", station.country]
        meta = ElidedLabel(" · ".join(p for p in parts if p))
        meta.setObjectName("stationMeta")
        quality = f"{station.codec} {station.bitrate}" if station.codec and station.bitrate else station.codec
        self.badge = QLabel(quality)
        self.badge.setObjectName("badge")
        self.badge.setVisible(bool(quality))
        self.play_button = QToolButton()
        self.play_button.setFixedSize(38, 38)
        self.play_button.setCursor(Qt.PointingHandCursor)
        self.play_button.clicked.connect(self.play_clicked)
        self.action_button = QToolButton()
        self.action_button.setFixedSize(38, 38)
        self.action_button.setCursor(Qt.PointingHandCursor)
        self.action_button.clicked.connect(self.action_clicked)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(name)
        texts.addWidget(meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(12)
        layout.addWidget(self.icon_label)
        layout.addLayout(texts, 1)
        layout.addWidget(self.badge)
        layout.addWidget(self.play_button)
        layout.addWidget(self.action_button)
        self.apply_theme()

    def apply_theme(self) -> None:
        self.icon_label.setPixmap(station_pixmap(self.station))
        self.play_button.setIcon(icons.icon("play", styles.TEXT, size=18))
        self.play_button.setIconSize(QSize(18, 18))
        self.play_button.setToolTip(tr("radio.play_tip"))
        if self.mode == "stations":
            self.action_button.setIcon(icons.icon("trash", styles.SUBTEXT, size=18))
            self.action_button.setToolTip(tr("radio.remove_tip"))
            self.action_button.setEnabled(True)
        else:
            self.action_button.setIcon(icons.icon("heart" if self._saved else "heart-outline",
                                                  styles.ACCENT if self._saved else styles.SUBTEXT, size=18))
            self.action_button.setToolTip(tr("radio.saved_tip") if self._saved else tr("radio.save_tip"))
            self.action_button.setEnabled(not self._saved)
        self.action_button.setIconSize(QSize(18, 18))

    def set_saved(self, saved: bool) -> None:
        self._saved = saved
        self.apply_theme()

    def set_playing(self, on: bool) -> None:
        self.setProperty("playing", on)
        self.style().unpolish(self)
        self.style().polish(self)


class MessagePane(QWidget):
    """Loading / empty / error state with an optional button."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.title = QLabel()
        self.title.setObjectName("heading")
        self.title.setAlignment(Qt.AlignCenter)
        self.hint = QLabel()
        self.hint.setObjectName("muted")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setFixedWidth(220)
        self.button = QPushButton()
        self.button.setObjectName("primary")
        self.button.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 0, 40, 40)
        layout.setSpacing(12)
        layout.addStretch(1)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)
        layout.addWidget(self.bar, 0, Qt.AlignHCenter)
        layout.addWidget(self.button, 0, Qt.AlignHCenter)
        layout.addStretch(2)

    def show_state(self, title: str, hint: str = "", *, loading: bool = False, action: str = "") -> None:
        self.title.setText(title)
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))
        self.bar.setVisible(loading)
        self.button.setText(action)
        self.button.setVisible(bool(action))


class RadioView(QWidget):
    play_requested = Signal(object)      # Station
    save_requested = Signal(object)
    remove_requested = Signal(object)
    summary_changed = Signal()

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self.mode = "stations"
        self._filter = ""
        self._tag = ""
        self._results: list[Station] = []
        self._loaded = False
        self._request = 0
        self._worker: AsyncWorker | None = None
        self._playing_url: str | None = None
        self._rows: list[StationRow] = []
        self._error = ""

        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        chips = QHBoxLayout()
        chips.setContentsMargins(22, 2, 18, 10)
        chips.setSpacing(8)
        self._chip_buttons: list[QPushButton] = []
        for tag in ("",) + CHIPS:
            chip = QPushButton()
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setProperty("tag", tag)
            chip.clicked.connect(lambda _checked=False, t=tag: self._pick_tag(t))
            self._chip_group.addButton(chip)
            self._chip_buttons.append(chip)
            chips.addWidget(chip)
        chips.addStretch(1)
        self._chips = QWidget()
        self._chips.setLayout(chips)
        self._chip_buttons[0].setChecked(True)

        self._list = QListWidget()
        self._list.setObjectName("stations")
        self._list.setSelectionMode(QAbstractItemView.NoSelection)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._list.setSpacing(0)
        self._list.setFocusPolicy(Qt.NoFocus)
        self._message = MessagePane()
        self._message.button.clicked.connect(self._retry)
        self._stack = QStackedLayout()
        self._stack.addWidget(self._list)
        self._stack.addWidget(self._message)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._chips)
        layout.addLayout(self._stack, 1)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(450)
        self._debounce.timeout.connect(self._search)
        self.retranslate()

    # -- public API -------------------------------------------------------------------------------
    def show_mode(self, mode: str) -> None:
        self.mode = mode
        self._chips.setVisible(mode == "explore")
        self._filter = ""
        if mode == "explore":
            self._search() if not self._loaded else self._populate(self._results)
        else:
            self._cancel()
            self._load_saved()

    def set_filter_text(self, text: str) -> None:
        self._filter = text.strip()
        if self.mode == "stations":
            self._load_saved()
        else:
            self._debounce.start()          # do not hit the network on every key press

    def refresh(self) -> None:
        """Saved stations changed (added/removed): reload My Stations, or re-mark the search results."""
        if self.mode == "stations":
            self._load_saved()
        else:
            saved = self._db.station_urls()
            for row in self._rows:
                row.set_saved(row.station.stream_url in saved)

    def set_playing_url(self, url: str | None) -> None:
        self._playing_url = url
        for row in self._rows:
            row.set_playing(bool(url) and row.station.stream_url == url)

    def refresh_icons(self) -> None:
        for row in self._rows:
            row.apply_theme()

    def apply_theme(self) -> None:
        self.refresh_icons()

    def summary(self) -> str:
        if self.mode == "stations":
            return trn("radio.count", len(self._rows))
        return tr("radio.source_note")

    def retranslate(self) -> None:
        for chip in self._chip_buttons:
            tag = chip.property("tag")
            chip.setText(tr("radio.popular") if not tag else tag.capitalize())
        for row in self._rows:
            row.apply_theme()
        if self._rows:
            return
        if self.mode == "stations":
            self._load_saved()

    def cancel(self) -> None:
        self._cancel()

    # -- saved stations ------------------------------------------------------------------------------
    def _load_saved(self) -> None:
        stations = self._db.stations()
        needle = normalize(self._filter)
        if needle:
            stations = [s for s in stations if all(t in normalize(f"{s.name} {s.tags} {s.country}") for t in needle.split())]
        self._show(stations, saved_all=True)
        if not stations:
            if self._filter:
                self._message.show_state(tr("radio.no_results"), tr("radio.no_results_hint"))
            else:
                self._message.show_state(tr("radio.stations_empty"), tr("radio.stations_empty_hint"))
            self._stack.setCurrentWidget(self._message)

    # -- explore ---------------------------------------------------------------------------------------
    def _pick_tag(self, tag: str) -> None:
        self._tag = tag
        self._search()

    def _retry(self) -> None:
        if self.mode == "explore":
            self._search()

    def _cancel(self) -> None:
        self._request += 1
        self._debounce.stop()
        if self._worker is not None:
            self._worker.cancel()

    def _search(self) -> None:
        if self.mode != "explore":
            return
        self._cancel()
        request, name, tag = self._request, self._filter, self._tag
        self._message.show_state(tr("radio.searching_stations"), loading=True)
        self._stack.setCurrentWidget(self._message)

        async def look(_progress):
            client = radio.RadioBrowserClient()
            try:
                return await client.search(name=name, tag=tag)
            finally:
                await client.aclose()

        worker = AsyncWorker(look, self)
        self._worker = worker
        worker.result.connect(lambda stations, r=request: self._found(stations, r))
        worker.failed.connect(lambda message, r=request: self._failed(message, r))
        worker.finished.connect(lambda w=worker: (setattr(self, "_worker", None) if self._worker is w else None, w.deleteLater()))
        worker.start()

    def _found(self, stations: list[Station], request: int) -> None:
        if request != self._request:
            return
        self._results, self._loaded = stations, True
        self._populate(stations)

    def _failed(self, message: str, request: int) -> None:
        if request != self._request or message == "cancelled":
            return
        self._loaded = False
        self._message.show_state(tr("radio.explore_failed"), tr("radio.explore_failed_hint", error=message), action=tr("radio.retry"))
        self._stack.setCurrentWidget(self._message)
        self.summary_changed.emit()

    def _populate(self, stations: list[Station]) -> None:
        self._show(stations, saved_all=False)
        if not stations:
            self._message.show_state(tr("radio.no_results"), tr("radio.no_results_hint"))
            self._stack.setCurrentWidget(self._message)

    # -- rows ------------------------------------------------------------------------------------------------
    def _show(self, stations: list[Station], saved_all: bool) -> None:
        self._list.setUpdatesEnabled(False)
        self._list.clear()
        self._rows.clear()
        saved = self._db.station_urls()
        for station in stations:
            row = StationRow(station, self.mode, saved_all or station.stream_url in saved)
            row.set_playing(self._playing_url == station.stream_url)
            row.play_clicked.connect(lambda s=station: self.play_requested.emit(s))
            row.action_clicked.connect(lambda s=station: (self.remove_requested if self.mode == "stations" else self.save_requested).emit(s))
            item = QListWidgetItem(self._list)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self._list.setItemWidget(item, row)
            self._rows.append(row)
        self._list.setUpdatesEnabled(True)
        if stations:
            self._stack.setCurrentWidget(self._list)
        self.summary_changed.emit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        item = self._list.itemAt(self._list.viewport().mapFrom(self, event.position().toPoint()))
        if item is not None:
            row = self._list.itemWidget(item)
            if isinstance(row, StationRow):
                self.play_requested.emit(row.station)
        super().mouseDoubleClickEvent(event)
