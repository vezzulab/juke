"""The page of a phone or tablet: what state it is in, how much room it has, and where songs are sent from."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QProgressBar,
                               QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ...config import AUDIO_EXTENSIONS
from ...db.folders import ordered
from ...devices import mtp
from ...i18n import tr, trn
from .. import icons, styles


def size_text(n: int) -> str:
    for unit, step in (("TB", 1 << 40), ("GB", 1 << 30), ("MB", 1 << 20)):
        if n >= step:
            return f"{n / step:.1f} {unit}" if n < 100 * step else f"{n / step:.0f} {unit}"
    return f"{n / 1024:.0f} KB"


WIDTH = 620                                # the centred column: wide enough for the four buttons in Spanish too


class DeviceView(QWidget):
    files_chosen = Signal(str, list)          # device key, files and folders picked here
    folder_chosen = Signal(str, int)          # device key, one of the user's Juke folders
    refresh_requested = Signal()
    cancel_requested = Signal()
    remove_requested = Signal(str, list)      # device key, the songs (devices.library.Song) to take off it
    eject_requested = Signal(str)             # device key

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._device: mtp.Device | None = None
        self._sending = False
        self._children: dict[int | None, list] = {}        # the user's folders, by parent id
        self._choice: dict[tuple[str, str], int] = {}      # which storage (memory or card) was picked, by kind of device
        self._songs: list = []                             # what is on the device (devices.library.Song)
        self._filter = ""
        self._reading = False
        self.glyph = QLabel(alignment=Qt.AlignCenter)
        self.title = QLabel(alignment=Qt.AlignCenter)
        self.title.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.title.setWordWrap(True)
        self.subtitle = QLabel(alignment=Qt.AlignCenter)
        self.subtitle.setObjectName("muted")
        self.hint = QLabel(alignment=Qt.AlignCenter)
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.hint.setMinimumWidth(WIDTH)          # the column is fixed wide: a wrapped label only gets its full height at a fixed width

        self.storage_box = QVBoxLayout()
        self.storage_box.setSpacing(10)
        self.target_label = QLabel()                       # only for a device with more than one place to write to
        self.target = QComboBox()
        self.target.setMinimumWidth(300)
        self.target.currentIndexChanged.connect(self._target_picked)
        target_row = QHBoxLayout()
        target_row.addStretch(1)
        target_row.addWidget(self.target_label)
        target_row.addWidget(self.target)
        target_row.addStretch(1)
        self.target_row = QWidget()
        self.target_row.setLayout(target_row)
        target_row.setContentsMargins(0, 0, 0, 0)
        self.send_juke = QPushButton()                     # the person's own folders inside Juke: the main way to fill a device
        self.send_juke.setObjectName("primary")
        self.send_juke.setCursor(Qt.PointingHandCursor)
        self.folder_menu = QMenu(self.send_juke)
        self.folder_menu.aboutToShow.connect(lambda: self._fill_menu(self.folder_menu, None))
        self.send_juke.setMenu(self.folder_menu)
        self.send_songs = QPushButton()
        self.send_songs.setCursor(Qt.PointingHandCursor)
        self.send_folder = QPushButton()
        self.send_folder.setCursor(Qt.PointingHandCursor)
        self.check = QPushButton()
        self.check.setCursor(Qt.PointingHandCursor)
        self.eject_alt = self._eject_button()               # for a device that cannot be used yet: it can still be put away
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        for button in (self.send_juke, self.send_songs, self.send_folder, self.check, self.eject_alt):
            buttons.addWidget(button)
        buttons.addStretch(1)

        self.progress_box = QFrame()
        self.progress_box.setObjectName("stationRow")
        inner = QVBoxLayout(self.progress_box)
        inner.setContentsMargins(16, 12, 16, 14)
        inner.setSpacing(8)
        top = QHBoxLayout()
        self.progress_label = QLabel()
        self.progress_name = QLabel()
        self.progress_name.setObjectName("muted")
        self.stop = QPushButton()
        self.stop.setCursor(Qt.PointingHandCursor)
        top.addWidget(self.progress_label)
        top.addStretch(1)
        top.addWidget(self.stop)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        inner.addLayout(top)
        inner.addWidget(self.progress_name)
        inner.addWidget(self.bar)
        self.progress_box.hide()

        self.drop_hint = QLabel(alignment=Qt.AlignCenter)
        self.drop_hint.setObjectName("muted")
        self.drop_hint.setWordWrap(True)
        self.drop_hint.setMinimumWidth(WIDTH)

        column = QVBoxLayout()
        column.setSpacing(12)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.glyph)
        column.addWidget(self.title)
        column.addWidget(self.subtitle)
        column.addSpacing(6)
        column.addWidget(self.hint)
        column.addSpacing(6)
        column.addLayout(self.storage_box)
        column.addWidget(self.target_row)
        column.addSpacing(10)
        column.addLayout(buttons)
        column.addSpacing(6)
        column.addWidget(self.progress_box)
        column.addWidget(self.drop_hint)
        holder = QWidget()
        holder.setFixedWidth(WIDTH)
        holder.setLayout(column)
        # what is on the device, the way iTunes showed an iPod: artists, their albums, their songs
        self.songs_status = QLabel()
        self.songs_status.setObjectName("muted")
        self.tree = _SongTree(self)
        self.tree.setObjectName("deviceSongs")
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setIndentation(20)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, self.tree.header().ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, self.tree.header().ResizeMode.ResizeToContents)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._song_menu)
        self.tree.remove_pressed.connect(self._remove_selected)
        self.songs_panel = QWidget()
        panel = QVBoxLayout(self.songs_panel)
        panel.setContentsMargins(22, 4, 14, 8)
        panel.setSpacing(6)
        self.eject = self._eject_button()
        status_row = QHBoxLayout()
        status_row.addWidget(self.songs_status, 1)
        status_row.addWidget(self.eject)
        panel.addLayout(status_row)
        panel.addWidget(self.tree, 1)
        self.songs_panel.hide()
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.addStretch(2)                                     # 0: above the header (only while it sits alone in the middle)
        self._outer.addWidget(holder, 0, Qt.AlignHCenter)             # 1
        self._outer.addWidget(self.songs_panel, 1)                    # 2
        self._outer.addStretch(3)                                     # 3
        self._fit(False)

        self.send_songs.clicked.connect(self._pick_songs)
        self.send_folder.clicked.connect(self._pick_folder)
        self.check.clicked.connect(self.refresh_requested)
        self.stop.clicked.connect(self.cancel_requested)
        styles.signals.changed.connect(lambda _n: self._paint_glyph())
        self.retranslate()
        self.show_device(None)

    def _eject_button(self) -> QPushButton:
        button = QPushButton()
        button.setCursor(Qt.PointingHandCursor)
        button.setIconSize(QSize(14, 14))
        button.clicked.connect(lambda: self._device and self.eject_requested.emit(self._device.key))
        return button

    def _fit(self, with_songs: bool) -> None:
        """The header alone sits in the middle; with the songs below it goes to the top and the list takes the rest."""
        self._outer.setStretch(0, 0 if with_songs else 2)
        self._outer.setStretch(2, 1 if with_songs else 0)
        self._outer.setStretch(3, 0 if with_songs else 3)
        if with_songs:
            self._outer.setContentsMargins(0, 8, 0, 0)
        else:
            self._outer.setContentsMargins(0, 0, 0, 0)

    # -- what is shown
    def _paint_glyph(self) -> None:
        self.glyph.setPixmap(icons.glyph("device", styles.ACCENT if self._device and self._device.state == "ready" else styles.MUTED, 56))

    def retranslate(self) -> None:
        self.send_juke.setText(tr("device.send_juke"))
        self.send_songs.setText(tr("device.send_songs"))
        self.send_folder.setText(tr("device.send_folder"))
        self.target_label.setText(tr("device.send_to"))
        self.check.setText(tr("device.check_again"))
        self.stop.setText(tr("device.cancel"))
        for button in (self.eject, self.eject_alt):
            button.setText(tr("device.eject"))
            button.setIcon(icons.icon("eject", styles.TEXT, size=14))
        self.show_device(self._device)

    def show_device(self, device: mtp.Device | None) -> None:
        self._device = device
        self._paint_glyph()
        while self.storage_box.count():
            item = self.storage_box.takeAt(0)
            gone = item.widget()
            if gone is not None:
                gone.hide()                                   # gone now, not whenever the event loop gets to deleting it
                gone.setParent(None)
                gone.deleteLater()
        if device is None:
            self._fill_targets(None)
            self.title.setText("")
            self.subtitle.setText("")
            self.hint.setText("")
            self.drop_hint.setText("")
            for widget in (self.send_juke, self.send_songs, self.send_folder, self.check, self.eject_alt):
                widget.hide()
            self.songs_panel.hide()
            self._fit(False)
            return
        ready, waiting, busy = device.state == "ready", device.state == "waiting", device.state == "busy"
        for widget in (self.glyph, self.title, self.subtitle):    # the window's own heading already names a ready device
            widget.setVisible(not ready)
        self.songs_panel.setVisible(ready)
        self.eject_alt.setVisible(not ready)
        self._fit(ready)
        name = device.label
        self.title.setText(name if ready else tr("device.waiting.title") if waiting else tr("device.busy.title", name=name))
        self.subtitle.setText(tr("device.subtitle") if ready else name if waiting else "")
        self.hint.setText(tr("device.waiting.hint", name=name) if waiting else tr("device.busy.hint") if busy else "")
        self.hint.setVisible(not ready)
        for label in (self.hint, self.drop_hint):             # a wrapped label needs its height set: the column is centred, not stretched
            label.setMinimumHeight(label.heightForWidth(WIDTH) if label.text() else 0)
        self.drop_hint.setText(tr("device.drop_hint", name=name) if ready else "")
        self.drop_hint.setVisible(ready and not self._sending and not self._songs and not self._reading)
        self.drop_hint.setMinimumHeight(self.drop_hint.heightForWidth(WIDTH) if ready else 0)
        for storage in device.storages:
            self.storage_box.addWidget(self._storage_row(storage))
        self._fill_targets(device if ready else None)
        self.send_juke.setVisible(ready)
        self.send_songs.setVisible(ready)
        self.send_folder.setVisible(ready)
        self.check.setVisible(not ready)
        self._enable()

    # -- where to write: the internal memory, or the card when there is one
    def _writable(self, device: mtp.Device | None) -> list[mtp.Storage]:
        return [s for s in device.storages if s.writable] if device else []

    def _fill_targets(self, device: mtp.Device | None) -> None:
        options = self._writable(device)
        self.target.blockSignals(True)
        self.target.clear()
        for storage in options:
            self.target.addItem(f"{storage.name or tr('device.storage_default')} · {tr('device.free', free=size_text(storage.free))}", storage.id)
        wanted = self._choice.get((device.vendor, device.product)) if device else None
        index = self.target.findData(wanted)
        self.target.setCurrentIndex(index if index >= 0 else 0)
        self.target.blockSignals(False)
        self.target_row.setVisible(len(options) > 1)

    def _target_picked(self, _index: int) -> None:
        if self._device is not None and self.target.currentData() is not None:
            self._choice[(self._device.vendor, self._device.product)] = self.target.currentData()

    def storage_for(self, device: mtp.Device) -> int | None:
        """The storage chosen for this kind of device, if it is still there (None: let the first one that is writable do)."""
        wanted = self._choice.get((device.vendor, device.product))
        return wanted if any(s.id == wanted for s in self._writable(device)) else None

    def _storage_row(self, storage: mtp.Storage) -> QWidget:
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        head = QHBoxLayout()
        label = QLabel(storage.name or tr("device.storage_default"))
        amount = QLabel(tr("device.storage", free=size_text(storage.free), total=size_text(storage.capacity)))
        amount.setObjectName("muted")
        head.addWidget(label)
        head.addStretch(1)
        head.addWidget(amount)
        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setValue(int(1000 * (storage.capacity - storage.free) / storage.capacity) if storage.capacity else 0)
        bar.setTextVisible(False)
        layout.addLayout(head)
        layout.addWidget(bar)
        return row

    # -- sending
    def _enable(self) -> None:
        for button in (self.send_juke, self.send_songs, self.send_folder):
            button.setEnabled(not self._sending)

    def set_sending(self, sending: bool) -> None:
        self._sending = sending
        self.progress_box.setVisible(sending)
        if not sending:
            self.bar.setValue(0)
        self._show_hint()
        self._enable()

    def set_progress(self, done: int, total: int, name: str, fraction: float) -> None:
        self.progress_label.setText(tr("device.sending", done=min(done + 1, total), total=total))
        self.progress_name.setText(name)
        self.bar.setValue(int(1000 * (done + fraction) / total) if total else 0)

    # -- the user's folders
    def set_folders(self, folders: list) -> None:
        self._children = {}
        for folder in folders:
            self._children.setdefault(folder.parent_id, []).append(folder)

    def _fill_menu(self, menu: QMenu, parent_id: int | None) -> None:
        """The folders as nested menus, each level built when it is opened; choosing one sends it with what is inside."""
        menu.clear()
        key = self._device.key if self._device else ""
        if parent_id is not None:
            menu.addAction(tr("menu.this_folder"), lambda _c=False, fid=parent_id: self.folder_chosen.emit(key, fid))
            menu.addSeparator()
        for folder in ordered(self._children.get(parent_id, []), "name"):
            label = f"{folder.name}  ({folder.count:,})"
            if self._children.get(folder.id):
                sub = menu.addMenu(label)
                sub.aboutToShow.connect(lambda m=sub, fid=folder.id: self._fill_menu(m, fid))
                sub.addAction("…")                            # so the entry opens; replaced when it does
            else:
                menu.addAction(label, lambda _c=False, fid=folder.id: self.folder_chosen.emit(key, fid)).setEnabled(folder.count > 0)
        if parent_id is None and not self._children.get(None):
            menu.addAction(tr("device.no_folders")).setEnabled(False)

    def _pick_songs(self) -> None:
        if not self._device:
            return
        patterns = " ".join(f"*{ext}" for ext in sorted(AUDIO_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(self, tr("device.dialog_songs"), "", f"{tr('device.filter')} ({patterns})")
        if files:
            self.files_chosen.emit(self._device.key, files)

    def _pick_folder(self) -> None:
        if not self._device:
            return
        folder = QFileDialog.getExistingDirectory(self, tr("device.dialog_folder"))
        if folder:
            self.files_chosen.emit(self._device.key, [folder])

    # -- what is on the device
    def set_reading(self, count: int | None) -> None:
        """A read of the device is under way (``count`` songs so far), or (None) it is over."""
        self._reading = count is not None
        if count is not None:
            self.songs_status.setText(tr("device.reading", n=f"{count:,}"))
        else:
            self._status()
        self._show_hint()

    def _show_hint(self) -> None:
        """How to fill the device, shown only while there is nothing on it to look at."""
        self.drop_hint.setVisible(bool(self._device and self._device.state == "ready") and not self._sending
                                  and not self._songs and not self._reading)

    def set_songs(self, songs: list) -> None:
        self._songs = list(songs)
        self._reading = False
        self._rebuild()
        self._show_hint()

    def clear_songs(self) -> None:
        self._songs = []
        self._rebuild()

    def filter(self, text: str) -> None:
        self._filter = text.strip().casefold()
        self._rebuild()

    def _status(self) -> None:
        shown = self._matching()
        if not self._songs:
            self.songs_status.setText(tr("device.no_music"))
        elif self._filter:
            self.songs_status.setText(trn("device.songs_found", len(shown)))
        else:
            self.songs_status.setText(trn("device.songs_on", len(self._songs)))

    def _matching(self) -> list:
        if not self._filter:
            return self._songs
        return [s for s in self._songs if self._filter in f"{s.artist} {s.album} {s.title}".casefold()]

    def _rebuild(self) -> None:
        shown = self._matching()
        tree = self.tree
        tree.setUpdatesEnabled(False)
        tree.clear()
        artists: dict[str, dict[str, list]] = {}
        for song in shown:
            artists.setdefault(song.artist, {}).setdefault(song.album, []).append(song)
        many = len({(s.storage) for s in self._songs}) > 1
        for artist in sorted(artists, key=str.casefold):
            albums = artists[artist]
            top = QTreeWidgetItem(tree, [artist or tr("unknown_artist"), trn("device.count", sum(len(v) for v in albums.values()))])
            for album in sorted(albums, key=lambda a: (a == "", a.casefold())):      # the albums first, loose songs after them
                node = top
                if album:
                    node = QTreeWidgetItem(top, [album, trn("device.count", len(albums[album]))])
                for song in sorted(albums[album], key=lambda s: s.filename.casefold()):
                    leaf = QTreeWidgetItem(node, [song.title, size_text(song.size) + (f" · {song.storage_name}" if many else "")])
                    leaf.setData(0, Qt.UserRole, song)
            top.setExpanded(bool(self._filter))
        if self._filter:
            tree.expandAll()
        stack = [tree.topLevelItem(row) for row in range(tree.topLevelItemCount())]
        while stack:                                                   # the numbers all line up on the right
            item = stack.pop()
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            stack.extend(item.child(i) for i in range(item.childCount()))
        tree.setUpdatesEnabled(True)
        if not self._reading:
            self._status()

    def _selected_songs(self) -> list:
        found, seen = [], set()

        def walk(item: QTreeWidgetItem) -> None:
            song = item.data(0, Qt.UserRole)
            if song is not None:
                if id(song) not in seen:
                    seen.add(id(song))
                    found.append(song)
                return
            for i in range(item.childCount()):
                walk(item.child(i))

        for item in self.tree.selectedItems():
            walk(item)
        return found

    def _song_menu(self, position) -> None:
        if not self._selected_songs() or not self._device or self._sending:
            return
        menu = QMenu(self)
        menu.addAction(tr("device.remove"), self._remove_selected)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _remove_selected(self) -> None:
        songs = self._selected_songs()
        if songs and self._device and not self._sending:
            self.remove_requested.emit(self._device.key, songs)


class _SongTree(QTreeWidget):
    remove_pressed = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.matches(QKeySequence.Delete) or event.key() == Qt.Key_Backspace:
            self.remove_pressed.emit()
            return
        super().keyPressEvent(event)
