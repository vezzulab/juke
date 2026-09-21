"""Left navigation: LIBRARY / SERVERS / RADIO / PLAYLISTS / FOLDERS, with expandable artist, album, genre groups."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QMimeData, QModelIndex, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetricsF, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QMenu, QStyle, QStyledItemDelegate, QToolTip, QTreeWidget,
                               QTreeWidgetItem)

from ...i18n import tr
from .. import icons, styles

KIND_ROLE = Qt.UserRole + 1     # header | item | group | child
KEY_ROLE = Qt.UserRole + 2      # (key, value)
COUNT_ROLE = Qt.UserRole + 3    # int | None
ACTION_ROLE = Qt.UserRole + 4   # "plus": header row with a "+" button on the right
ICON_ROLE = Qt.UserRole + 5     # (glyph, size): lets the icons be rebuilt when the theme changes
SOURCE_ROLE = Qt.UserRole + 6   # the directory a folder mirrors on disk, or None
SORT_ROLE = Qt.UserRole + 7     # how the folders inside a folder are ordered
PLUS = 26                       # size of that button, px

MIME_TRACKS = "application/x-juke-tracks"    # JSON list of track ids, dragged out of the song table
MIME_FOLDER = "application/x-juke-folder"    # the id of a folder of the sidebar, dragged onto another

GROUPS = {"artists": "artist", "albums": "album", "genres": "genre"}


class SidebarDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index: QModelIndex) -> QSize:
        kind = index.data(KIND_ROLE)
        height = {"header": 34, "item": 36, "group": 36, "child": 30, "folder": 32, "folderleaf": 32}.get(kind, 34)
        return QSize(option.rect.width(), height)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        kind = index.data(KIND_ROLE)
        rect = QRectF(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if kind == "header":
            font = QFont(option.font)
            font.setPixelSize(10)
            font.setBold(True)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 1.3)
            painter.setFont(font)
            painter.setPen(QColor(styles.MUTED))
            painter.drawText(rect.adjusted(12, 8, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, index.data(Qt.DisplayRole))
            if getattr(option.widget, "drop_index", None) == index:
                painter.setPen(QPen(QColor(styles.ACCENT), 1.4))
                painter.setBrush(styles.qcolor(styles.ACCENT, 30))
                painter.drawRoundedRect(rect.adjusted(6, 4, -6, -2), 9, 9)
            if index.data(ACTION_ROLE) == "plus":
                hover = getattr(option.widget, "plus_hover", "") == index.data(KEY_ROLE)
                box = QRectF(rect.right() - PLUS - 10, rect.top() + 6, PLUS, PLUS)
                if hover:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(styles.qcolor(styles.OVERLAY, 230))
                    painter.drawRoundedRect(box, 8, 8)
                painter.setPen(QPen(QColor(styles.TEXT if hover else styles.SUBTEXT), 1.9, Qt.SolidLine, Qt.RoundCap))
                c = box.center()
                painter.drawLine(QPointF(c.x() - 5, c.y()), QPointF(c.x() + 5, c.y()))
                painter.drawLine(QPointF(c.x(), c.y() - 5), QPointF(c.x(), c.y() + 5))
            painter.restore()
            return

        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        pill = rect.adjusted(0, 1, 0, -1)
        if selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(styles.qcolor(styles.ACCENT, 46))
            painter.drawRoundedRect(pill, 9, 9)
            painter.setBrush(QColor(styles.ACCENT))
            painter.drawRoundedRect(QRectF(pill.left(), pill.center().y() - 8, 3, 16), 1.5, 1.5)
        elif hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(styles.qcolor(styles.SURFACE, 150))
            painter.drawRoundedRect(pill, 9, 9)
        if getattr(option.widget, "drop_index", None) == index:
            painter.setPen(QPen(QColor(styles.ACCENT), 1.6))
            painter.setBrush(styles.qcolor(styles.ACCENT, 40))
            painter.drawRoundedRect(pill.adjusted(1, 1, -1, -1), 9, 9)

        depth, parent = 0, index.parent()
        while parent.isValid():
            depth += 1
            parent = parent.parent()
        x = pill.left() + 12 + max(0, depth - 1) * 14
        icon = index.data(Qt.DecorationRole)
        if isinstance(icon, QIcon) and kind != "child":
            side = 16 if kind in ("folder", "folderleaf") else 18
            state = QIcon.On if selected else QIcon.Off
            pixmap = icon.pixmap(QSize(side, side), QIcon.Normal, state)
            painter.drawPixmap(int(x), int(pill.center().y() - side / 2), pixmap)
            x += side + 12

        right = pill.right() - 12
        count = index.data(COUNT_ROLE)
        if kind in ("group", "folder"):
            painter.setPen(QPen(QColor(styles.MUTED), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            cx, cy = right - 4, pill.center().y()
            if option.state & QStyle.State_Open:
                painter.drawLine(int(cx - 4), int(cy - 2), int(cx), int(cy + 2))
                painter.drawLine(int(cx), int(cy + 2), int(cx + 4), int(cy - 2))
            else:
                painter.drawLine(int(cx - 2), int(cy - 4), int(cx + 2), int(cy))
                painter.drawLine(int(cx + 2), int(cy), int(cx - 2), int(cy + 4))
            right -= 20
        if count is not None:
            font = QFont(option.font)
            font.setPixelSize(11)
            painter.setFont(font)
            painter.setPen(QColor(styles.MUTED))
            label = f"{count:,}"
            width = painter.fontMetrics().horizontalAdvance(label)
            painter.drawText(QRectF(right - width, pill.top(), width, pill.height()), Qt.AlignVCenter | Qt.AlignRight, label)
            right -= width + 10

        font = QFont(option.font)
        font.setPixelSize(13)
        font.setWeight(QFont.DemiBold if selected else QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor(styles.TEXT if selected or kind not in ("child", "folder", "folderleaf") else styles.SUBTEXT))
        text = painter.fontMetrics().elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight, int(right - x))
        painter.drawText(QRectF(x, pill.top(), right - x, pill.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()


class Sidebar(QTreeWidget):
    """Emits ``selected(key, value)``: ("all", None), ("artist", "Name"), ("list", "queue")..."""

    selected = Signal(str, object)
    new_playlist_requested = Signal()
    rename_playlist_requested = Signal(int)
    delete_playlist_requested = Signal(int)
    new_folder_requested = Signal(int)              # parent folder id, 0 for the top level
    rename_folder_requested = Signal(int)
    delete_folder_requested = Signal(int)
    folder_action_requested = Signal(str, int)      # "play" | "shuffle" | "queue" | "reveal" | "duplicate", folder id
    sort_folders_requested = Signal(int, str)       # parent folder id (0 = top level), mode
    restore_removed_requested = Signal()
    tracks_dropped = Signal(str, int, list)         # "playlist" | "folder", its id, track ids
    paths_dropped = Signal(int, list)               # folder id (0 = top level), files and directories from outside
    folder_moved = Signal(int, int)                 # folder id, new parent id (0 = top level)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setHeaderHidden(True)
        self.setIndentation(0)
        self.setRootIsDecorated(False)
        self.setExpandsOnDoubleClick(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setFixedWidth(250)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(False)
        self.drop_index = QModelIndex()                # the row a drag is hovering over
        self._hover_expand = QTimer(self)
        self._hover_expand.setSingleShot(True)
        self._hover_expand.setInterval(650)
        self._hover_expand.timeout.connect(self._expand_hovered)
        self.setItemDelegate(SidebarDelegate(self))
        self._groups_data: dict[str, list[tuple[str, int]]] = {"artists": [], "albums": [], "genres": []}
        self._filled: set[str] = set()
        self._headers: dict[str, QTreeWidgetItem] = {}
        self._items: dict[tuple[str, object], QTreeWidgetItem] = {}
        self._before_click: QTreeWidgetItem | None = None
        self.plus_hover: tuple | None = None           # the header (key) whose "+" the mouse is on
        self._folder_tree: dict = {}   # nested {name: {subname: {...}}} of the server's folders
        self._user_folders: dict[int | None, list] = {}    # parent id -> the folders (Music.juke) directly below it
        self._folder_by_id: dict[int, object] = {}
        self._root_sort = "name"

        def header(name: str) -> QTreeWidgetItem:
            item = QTreeWidgetItem(self, [""])
            item.setData(0, KIND_ROLE, "header")
            item.setData(0, KEY_ROLE, ("header", name))
            item.setFlags(Qt.ItemIsEnabled)
            self._headers[name] = item
            return item

        def entry(parent: QTreeWidgetItem, key: str, glyph: str, kind: str = "item") -> QTreeWidgetItem:
            item = QTreeWidgetItem(parent, [""])
            item.setData(0, KIND_ROLE, kind)
            item.setData(0, KEY_ROLE, (key, None))
            item.setData(0, COUNT_ROLE, None)
            item.setIcon(0, icons.icon(glyph, styles.SUBTEXT, active=styles.ACCENT, size=18))
            item.setData(0, ICON_ROLE, (glyph, 18))
            self._items[(key, None)] = item
            return item

        library = header("library")
        for key, glyph, kind in (("all", "note", "item"), ("artists", "artist", "group"),
                                 ("albums", "album", "group"), ("genres", "genre", "group")):
            entry(library, key, glyph, kind)
        servers = header("servers")
        entry(servers, "airsonic", "server", "group")
        radio = header("radio")
        entry(radio, "stations", "radio")
        entry(radio, "explore", "globe")
        lists = header("lists")
        lists.setData(0, ACTION_ROLE, "plus")
        folders = header("folders")
        folders.setData(0, ACTION_ROLE, "plus")
        self.expandItem(library)
        self.expandItem(servers)
        self.expandItem(radio)
        self.expandItem(lists)
        self.expandItem(folders)

        self.itemClicked.connect(self._clicked)
        self.itemExpanded.connect(self._expanded)
        self.itemSelectionChanged.connect(self._selection_changed)
        self.retranslate()
        self.select("all")

    # -- data -----------------------------------------------------------------------------
    def set_groups(self, artists: list, albums: list, genres: list) -> None:
        self._groups_data = {"artists": artists, "albums": albums, "genres": genres}
        for name in list(self._filled):
            if name in GROUPS:
                self._fill_group(name)

    def set_folders(self, paths: list[str]) -> None:
        """Server folder paths ("Artist/Album") -> a browsable tree under Airsonic."""
        tree: dict = {}
        for path in paths:
            node = tree
            for part in path.split("/"):
                node = node.setdefault(part, {})
        self._folder_tree = tree
        if "airsonic" in self._filled:
            self._fill_folders()

    def _fill_folders(self) -> None:
        group = self._items[("airsonic", None)]
        current = self.current_key()
        self.setUpdatesEnabled(False)
        self.blockSignals(True)
        for child in group.takeChildren():
            self._forget(child)
        self._add_folder_items(group, self._folder_tree, "")
        self._filled.add("airsonic")
        self.blockSignals(False)
        self.setUpdatesEnabled(True)
        if current in self._items:
            self.select(*current)

    def _forget(self, item: QTreeWidgetItem) -> None:
        for i in range(item.childCount()):
            self._forget(item.child(i))
        self._items.pop(item.data(0, KEY_ROLE), None)

    def _add_folder_items(self, parent: QTreeWidgetItem, subtree: dict, prefix: str) -> None:
        folder_icon = icons.icon("folder", styles.MUTED, active=styles.ACCENT, size=16)
        for name in sorted(subtree, key=str.casefold):
            path = f"{prefix}{name}"
            item = QTreeWidgetItem(parent, [name])
            item.setData(0, KIND_ROLE, "folder" if subtree[name] else "folderleaf")
            item.setData(0, KEY_ROLE, ("folder", path))
            item.setIcon(0, folder_icon)
            item.setData(0, ICON_ROLE, ("folder", 16))
            self._items[("folder", path)] = item

    def _subtree_for(self, path: str) -> dict:
        node = self._folder_tree
        for part in path.split("/"):
            node = node.get(part, {})
        return node

    def set_counts(self, **counts: int | None) -> None:
        for key, value in counts.items():
            item = self._items.get((key, None))
            if item is not None:
                item.setData(0, COUNT_ROLE, value)
        self.viewport().update()

    def _fill_group(self, name: str) -> None:
        group = self._items[(name, None)]
        current = self.current_key()
        child_key = GROUPS[name]
        self.setUpdatesEnabled(False)
        self.blockSignals(True)
        for child in group.takeChildren():
            self._items.pop(child.data(0, KEY_ROLE), None)
        unknown = tr("unknown_" + child_key)
        for value, count in self._groups_data[name]:
            child = QTreeWidgetItem(group, [value or unknown])
            child.setData(0, KIND_ROLE, "child")
            key = (child_key, value)
            child.setData(0, KEY_ROLE, key)
            child.setData(0, COUNT_ROLE, count)
            self._items[key] = child
        self._filled.add(name)
        self.blockSignals(False)
        self.setUpdatesEnabled(True)
        if current in self._items:
            self.select(*current)

    # -- selection -------------------------------------------------------------------------
    def current_key(self) -> tuple[str, object] | None:
        item = self.currentItem()
        return item.data(0, KEY_ROLE) if item else None

    def select(self, key: str, value: object = None) -> None:
        item = self._items.get((key, value))
        if item is not None:
            self.blockSignals(True)
            self.setCurrentItem(item)
            self.blockSignals(False)
            self.viewport().update()

    def clear_selection(self) -> None:
        """Nothing highlighted: the view on screen is not one of the sidebar's (a search for copies, say)."""
        self.blockSignals(True)
        self.setCurrentItem(None)
        self.clearSelection()
        self.blockSignals(False)
        self.viewport().update()

    def _selection_changed(self) -> None:
        current = self.current_key()
        if current:
            self.selected.emit(*current)

    # -- the "+" next to PLAYLISTS and FOLDERS ---------------------------------------------------
    _PLUS_HEADERS = ("lists", "folders")

    def _plus_rect(self, name: str) -> QRect:
        header = self.visualItemRect(self._headers[name])
        return QRect(header.right() - PLUS - 10, header.top() + 6, PLUS, PLUS)

    def _plus_at(self, pos) -> str | None:
        return next((n for n in self._PLUS_HEADERS if self._plus_rect(n).contains(pos)), None)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        name = self._plus_at(event.position().toPoint())
        hover = ("header", name) if name else None
        if hover != self.plus_hover:
            self.plus_hover = hover
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self.plus_hover:
            self.plus_hover = None
            self.viewport().update()
        super().leaveEvent(event)

    def viewportEvent(self, event) -> bool:  # noqa: N802
        if event.type() == QEvent.ToolTip:
            name = self._plus_at(event.pos())
            if name:
                QToolTip.showText(event.globalPos(), tr("playlist.new" if name == "lists" else "folder.new"), self.viewport())
                return True
        return super().viewportEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            name = self._plus_at(event.position().toPoint())
            if name:
                (self.new_playlist_requested.emit() if name == "lists" else self.new_folder_requested.emit(0))
                event.accept()
                return
        self._before_click = self.currentItem()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = self.current_key()
        if key and key[0] in ("playlist", "ufolder"):
            if event.key() == Qt.Key_F2:
                (self.rename_playlist_requested if key[0] == "playlist" else self.rename_folder_requested).emit(int(key[1]))
                return
            if event.key() == Qt.Key_Delete:
                (self.delete_playlist_requested if key[0] == "playlist" else self.delete_folder_requested).emit(int(key[1]))
                return
        super().keyPressEvent(event)

    # -- right click ---------------------------------------------------------------------------------
    def contextMenuEvent(self, event) -> None:  # noqa: N802
        item = self.itemAt(event.pos())
        key = item.data(0, KEY_ROLE) if item else None
        menu = QMenu(self)
        if key and key[0] == "playlist":
            menu.addAction(tr("menu.rename"), lambda _c=False, pid=key[1]: self.rename_playlist_requested.emit(pid))
            menu.addAction(tr("menu.delete"), lambda _c=False, pid=key[1]: self.delete_playlist_requested.emit(pid))
        elif key and key[0] == "ufolder":
            self._folder_menu(menu, item, int(key[1]))
        elif item is self._headers["folders"]:
            menu.addAction(tr("menu.new_folder"), lambda: self.new_folder_requested.emit(0))
            self._sort_menu(menu, 0, self._root_sort)
            menu.addSeparator()
            menu.addAction(tr("menu.restore_removed"), self.restore_removed_requested.emit)
        elif item is self._headers["lists"]:
            menu.addAction(tr("menu.new_playlist"), self.new_playlist_requested.emit)
        else:
            return
        menu.exec(event.globalPos())

    def _sort_menu(self, menu: QMenu, parent_id: int, current: str) -> None:
        sort = menu.addMenu(tr("menu.sort_folders"))
        for mode in ("name", "name_desc", "number", "number_desc", "newest", "oldest"):
            action = sort.addAction(tr("sort." + mode), lambda _c=False, m=mode: self.sort_folders_requested.emit(parent_id, m))
            action.setCheckable(True)
            action.setChecked(mode == current)

    def _folder_menu(self, menu: QMenu, item: QTreeWidgetItem, folder_id: int) -> None:
        act = self.folder_action_requested.emit
        menu.addAction(tr("menu.play"), lambda: act("play", folder_id))
        menu.addAction(tr("menu.shuffle"), lambda: act("shuffle", folder_id))
        menu.addAction(tr("menu.add_to_queue"), lambda: act("queue", folder_id))
        menu.addSeparator()
        menu.addAction(tr("menu.new_subfolder"), lambda: self.new_folder_requested.emit(folder_id))
        menu.addAction(tr("menu.rename"), lambda: self.rename_folder_requested.emit(folder_id))
        menu.addAction(tr("menu.duplicate"), lambda: act("duplicate", folder_id))
        self._sort_menu(menu, folder_id, item.data(0, SORT_ROLE) or "name")
        menu.addSeparator()
        if item.data(0, SOURCE_ROLE):
            menu.addAction(tr("menu.show_in_files"), lambda: act("reveal", folder_id))
        menu.addAction(tr("menu.delete"), lambda: self.delete_folder_requested.emit(folder_id))

    # -- the user's folders (Music.juke) ---------------------------------------------------------------
    def set_user_folders(self, folders: list, root_sort: str = "name") -> None:
        """``folders``: the tree of db.folders.Folder. Only the levels that are open are built."""
        self._user_folders = {}
        self._folder_by_id = {f.id: f for f in folders}
        for f in folders:
            self._user_folders.setdefault(f.parent_id, []).append(f)
        self._root_sort = root_sort
        header = self._headers["folders"]
        expanded = {k[1] for k, it in self._items.items() if k[0] == "ufolder" and it.isExpanded()}
        current = self.current_key()
        self.setUpdatesEnabled(False)
        self.blockSignals(True)
        for child in header.takeChildren():
            self._forget(child)
        self._add_user_children(header, None)
        self.blockSignals(False)

        def reopen(parent: QTreeWidgetItem) -> None:
            for i in range(parent.childCount()):
                child = parent.child(i)
                child_key = child.data(0, KEY_ROLE)
                if child_key and child_key[1] in expanded and child.data(0, KIND_ROLE) == "folder":
                    child.setExpanded(True)          # builds its own children
                    reopen(child)

        reopen(header)
        self.setUpdatesEnabled(True)
        if current in self._items:
            self.select(*current)
        self.viewport().update()

    def _add_user_children(self, parent_item: QTreeWidgetItem, parent_id: int | None) -> None:
        from ...db.folders import ordered

        mode = self._root_sort if parent_id is None else self._folder_by_id[parent_id].sort_mode
        icon = icons.icon("folder", styles.MUTED, active=styles.ACCENT, size=16)
        for folder in ordered(self._user_folders.get(parent_id, []), mode):
            item = QTreeWidgetItem(parent_item, [folder.name])
            item.setData(0, KIND_ROLE, "folder" if self._user_folders.get(folder.id) else "folderleaf")
            item.setData(0, KEY_ROLE, ("ufolder", folder.id))
            item.setData(0, COUNT_ROLE, folder.count)
            item.setData(0, SOURCE_ROLE, folder.source_path)
            item.setData(0, SORT_ROLE, folder.sort_mode)
            item.setIcon(0, icon)
            item.setData(0, ICON_ROLE, ("folder", 16))
            self._items[("ufolder", folder.id)] = item

    def reveal_folder(self, folder_id: int) -> None:
        """Open the branches above a folder so it is on screen, and select it."""
        item = self._items.get(("ufolder", folder_id))
        if item is None:
            chain, node = [], self._folder_by_id.get(folder_id)
            while node is not None and node.parent_id is not None:
                chain.append(node.parent_id)
                node = self._folder_by_id.get(node.parent_id)
            for ancestor in reversed(chain):
                parent = self._items.get(("ufolder", ancestor))
                if parent is not None:
                    parent.setExpanded(True)
            item = self._items.get(("ufolder", folder_id))
        if item is not None:
            self.select("ufolder", folder_id)
            self.scrollToItem(item)

    # -- drag and drop ---------------------------------------------------------------------------------
    def startDrag(self, supported_actions) -> None:  # noqa: N802
        key = self.current_key()
        if not key or key[0] != "ufolder":
            return
        mime = QMimeData()
        mime.setData(MIME_FOLDER, str(int(key[1])).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        label = self.currentItem().text(0)
        font = QFont(self.font())
        font.setPixelSize(13)
        width = QFontMetricsF(font).horizontalAdvance(label) + 34
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
        drag.exec(Qt.MoveAction)

    def _drop_kind(self, mime, item: QTreeWidgetItem | None) -> str | None:
        """What a drag may do to ``item``: "playlist", "folder" or "top" (the FOLDERS heading); None if nothing."""
        if item is None:
            return None
        key = item.data(0, KEY_ROLE)
        kind = key[0] if key else None
        top = item is self._headers["folders"]
        if mime.hasFormat(MIME_TRACKS):
            return "playlist" if kind == "playlist" else "folder" if kind == "ufolder" else None
        if mime.hasFormat(MIME_FOLDER) or mime.hasUrls():
            return "folder" if kind == "ufolder" else "top" if top else None
        return None

    def _set_drop_item(self, item: QTreeWidgetItem | None) -> None:
        index = self.indexFromItem(item) if item is not None else QModelIndex()
        if index != self.drop_index:
            self.drop_index = index
            self.viewport().update()
        self._hover_expand.stop()
        if item is not None and item.data(0, KIND_ROLE) == "folder" and not item.isExpanded():
            self._hover_expand.start()

    def _expand_hovered(self) -> None:
        item = self.itemFromIndex(self.drop_index) if self.drop_index.isValid() else None
        if item is not None:
            item.setExpanded(True)

    def _understands(self, mime) -> bool:
        return mime.hasFormat(MIME_TRACKS) or mime.hasFormat(MIME_FOLDER) or mime.hasUrls()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        # The drag must be accepted on the way in whatever is under the pointer: a widget that refuses the
        # enter never hears the moves or the drop, so a drag that happened to arrive over a heading would die
        # there. Which row can take it is decided in dragMoveEvent.
        if self._understands(event.mimeData()):
            self.dragMoveEvent(event)               # lights the row under the pointer, if it can take the drag
            event.acceptProposedAction()            # ...and the enter itself stays accepted either way
        else:
            event.ignore()

    @staticmethod
    def _action_for(event) -> Qt.DropAction | None:
        """The action to answer with. Files dragged in from outside are only ever *copied*: answering "move"
        would tell the file manager to delete the originals once they are dropped."""
        mime = event.mimeData()
        if mime.hasFormat(MIME_FOLDER):
            return Qt.MoveAction
        if mime.hasFormat(MIME_TRACKS):
            return Qt.CopyAction
        possible = event.possibleActions()
        if possible & Qt.CopyAction:
            return Qt.CopyAction
        return Qt.LinkAction if possible & Qt.LinkAction else None

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        item = self.itemAt(event.position().toPoint())
        action = self._action_for(event)
        if action is not None and self._drop_kind(event.mimeData(), item):
            self._set_drop_item(item)
            event.setDropAction(action)
            event.accept()
        else:
            self._set_drop_item(None)
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_drop_item(None)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802
        item = self.itemAt(event.position().toPoint())
        mime = event.mimeData()
        kind = self._drop_kind(mime, item) if self._action_for(event) is not None else None
        self._set_drop_item(None)
        if not kind:
            event.ignore()
            return
        key = item.data(0, KEY_ROLE)
        target = int(key[1]) if kind in ("folder", "playlist") else 0
        if mime.hasFormat(MIME_TRACKS):
            import json

            try:
                ids = [int(i) for i in json.loads(bytes(mime.data(MIME_TRACKS)).decode())]
            except (ValueError, TypeError):
                ids = []
            if ids:
                self.tracks_dropped.emit(kind, target, ids)
        elif mime.hasFormat(MIME_FOLDER):
            self.folder_moved.emit(int(bytes(mime.data(MIME_FOLDER)).decode()), target)
        else:
            paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            if paths:
                self.paths_dropped.emit(target, paths)
        event.setDropAction(self._action_for(event) or Qt.CopyAction)
        event.accept()

    def set_playlists(self, playlists: list[tuple[int, str, int]]) -> None:
        """(id, name, count) of the user's playlists, shown under PLAYLISTS after Current Queue."""
        lists = self._headers["lists"]
        current = self.current_key()
        self.blockSignals(True)
        for key in [k for k in self._items if k[0] == "playlist"]:
            lists.removeChild(self._items.pop(key))
        icon = icons.icon("playlist", styles.SUBTEXT, active=styles.ACCENT, size=18)
        for playlist_id, name, count in playlists:
            item = QTreeWidgetItem(lists, [name])
            item.setData(0, KIND_ROLE, "item")
            item.setData(0, KEY_ROLE, ("playlist", playlist_id))
            item.setData(0, COUNT_ROLE, count)
            item.setIcon(0, icon)
            item.setData(0, ICON_ROLE, ("playlist", 18))
            self._items[("playlist", playlist_id)] = item
        self.blockSignals(False)
        if current in self._items:
            self.select(*current)
        self.viewport().update()

    def _clicked(self, item: QTreeWidgetItem) -> None:
        if item.data(0, KIND_ROLE) not in ("group", "folder"):
            return
        item.setExpanded(not item.isExpanded())
        if self._before_click is item:  # re-clicking the selected group: show its view again
            self.selected.emit(*item.data(0, KEY_ROLE))

    def _expanded(self, item: QTreeWidgetItem) -> None:
        key = item.data(0, KEY_ROLE)
        if not key:
            return
        if key[0] in GROUPS and key[0] not in self._filled:
            self._fill_group(key[0])
        elif key[0] == "airsonic" and "airsonic" not in self._filled:
            self._fill_folders()
        elif key[0] == "folder" and item.childCount() == 0:
            self._add_folder_items(item, self._subtree_for(key[1]), key[1] + "/")
        elif key[0] == "ufolder" and item.childCount() == 0:
            self.blockSignals(True)
            self._add_user_children(item, int(key[1]))
            self.blockSignals(False)

    def apply_theme(self) -> None:
        for item in self._items.values():
            spec = item.data(0, ICON_ROLE)
            if spec:
                item.setIcon(0, icons.icon(spec[0], styles.SUBTEXT if spec[0] != "folder" else styles.MUTED,
                                           active=styles.ACCENT, size=spec[1]))
        self.viewport().update()

    def retranslate(self) -> None:
        titles = {"library": "sidebar.library", "servers": "sidebar.servers", "radio": "sidebar.radio",
                  "lists": "sidebar.lists", "folders": "sidebar.folders"}
        for name, item in self._headers.items():
            item.setText(0, tr(titles[name]).upper())
        names = {"all": "sidebar.all", "artists": "sidebar.artists", "albums": "sidebar.albums",
                 "genres": "sidebar.genres", "airsonic": "sidebar.airsonic", "stations": "sidebar.stations",
                 "explore": "sidebar.explore"}
        for key, label in names.items():
            self._items[(key, None)].setText(0, tr(label))
        for name in list(self._filled):
            if name in GROUPS:
                self._fill_group(name)
        self.viewport().update()
