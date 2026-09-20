"""Left navigation: BIBLIOTECA / SERVIDORES / LISTAS with expandable artist, album, genre groups."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QMenu, QStyle, QStyledItemDelegate, QToolTip, QTreeWidget,
                               QTreeWidgetItem)

from ...i18n import tr
from .. import icons, styles

KIND_ROLE = Qt.UserRole + 1     # header | item | group | child
KEY_ROLE = Qt.UserRole + 2      # (key, value)
COUNT_ROLE = Qt.UserRole + 3    # int | None
ACTION_ROLE = Qt.UserRole + 4   # "plus": header row with a "+" button on the right
ICON_ROLE = Qt.UserRole + 5     # (glyph, size): lets the icons be rebuilt when the theme changes
PLUS = 26                       # size of that button, px

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
            if index.data(ACTION_ROLE) == "plus":
                hover = bool(getattr(option.widget, "plus_hover", False))
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
        self.setItemDelegate(SidebarDelegate(self))
        self._groups_data: dict[str, list[tuple[str, int]]] = {"artists": [], "albums": [], "genres": []}
        self._filled: set[str] = set()
        self._headers: dict[str, QTreeWidgetItem] = {}
        self._items: dict[tuple[str, object], QTreeWidgetItem] = {}
        self._before_click: QTreeWidgetItem | None = None
        self.plus_hover = False
        self._folder_tree: dict = {}   # nested {name: {subname: {...}}} of the server's folders

        def header(name: str) -> QTreeWidgetItem:
            item = QTreeWidgetItem(self, [""])
            item.setData(0, KIND_ROLE, "header")
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
        for key, glyph in (("favorites", "heart"), ("recent", "clock"), ("queue", "queue")):
            entry(lists, key, glyph)
        self.expandItem(library)
        self.expandItem(servers)
        self.expandItem(radio)
        self.expandItem(lists)

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

    def _selection_changed(self) -> None:
        current = self.current_key()
        if current:
            self.selected.emit(*current)

    # -- the "+" next to PLAYLISTS -----------------------------------------------------------
    def _plus_rect(self) -> QRect:
        header = self.visualItemRect(self._headers["lists"])
        return QRect(header.right() - PLUS - 10, header.top() + 6, PLUS, PLUS)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hover = self._plus_rect().contains(event.position().toPoint())
        if hover != self.plus_hover:
            self.plus_hover = hover
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self.plus_hover:
            self.plus_hover = False
            self.viewport().update()
        super().leaveEvent(event)

    def viewportEvent(self, event) -> bool:  # noqa: N802
        if event.type() == QEvent.ToolTip and self._plus_rect().contains(event.pos()):
            QToolTip.showText(event.globalPos(), tr("playlist.new"), self.viewport())
            return True
        return super().viewportEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._plus_rect().contains(event.position().toPoint()):
            self.new_playlist_requested.emit()
            event.accept()
            return
        self._before_click = self.currentItem()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        item = self.itemAt(event.pos())
        key = item.data(0, KEY_ROLE) if item else None
        menu = QMenu(self)
        if key and key[0] == "playlist":
            menu.addAction(tr("menu.rename"), lambda _c=False, pid=key[1]: self.rename_playlist_requested.emit(pid))
            menu.addAction(tr("menu.delete"), lambda _c=False, pid=key[1]: self.delete_playlist_requested.emit(pid))
        elif item is self._headers["lists"] or (key and key[0] in ("favorites", "recent", "queue")):
            menu.addAction(tr("menu.new_playlist"), self.new_playlist_requested.emit)
        else:
            return
        menu.exec(event.globalPos())

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

    def apply_theme(self) -> None:
        for item in self._items.values():
            spec = item.data(0, ICON_ROLE)
            if spec:
                item.setIcon(0, icons.icon(spec[0], styles.SUBTEXT if spec[0] != "folder" else styles.MUTED,
                                           active=styles.ACCENT, size=spec[1]))
        self.viewport().update()

    def retranslate(self) -> None:
        titles = {"library": "sidebar.library", "servers": "sidebar.servers", "radio": "sidebar.radio", "lists": "sidebar.lists"}
        for name, item in self._headers.items():
            item.setText(0, tr(titles[name]).upper())
        names = {"all": "sidebar.all", "artists": "sidebar.artists", "albums": "sidebar.albums",
                 "genres": "sidebar.genres", "airsonic": "sidebar.airsonic", "favorites": "sidebar.favorites",
                 "recent": "sidebar.recent", "queue": "sidebar.queue", "stations": "sidebar.stations",
                 "explore": "sidebar.explore"}
        for key, label in names.items():
            self._items[(key, None)].setText(0, tr(label))
        for name in list(self._filled):
            if name in GROUPS:
                self._fill_group(name)
        self.viewport().update()
