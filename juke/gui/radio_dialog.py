"""Add a radio station by pasting any web address; Juke works out where the audio is."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from ..api import radio
from ..api.radio_resolver import normalize_url, resolve_stations
from ..db.database import Station
from ..i18n import tr, trn
from ..workers import AsyncWorker
from . import icons, styles
from .components.widgets import ElidedLabel


class AddStationDialog(QDialog):
    def __init__(self, parent=None, resolver=None) -> None:
        super().__init__(parent)
        self._resolver = resolver or resolve_stations
        self._found: list[dict] = []
        self._address = ""
        self._worker: AsyncWorker | None = None
        self.setWindowTitle(tr("radio.add_title"))
        self.setMinimumWidth(520)

        prompt = QLabel(tr("radio.add_prompt"))
        prompt.setWordWrap(True)
        self.url = QLineEdit()
        self.url.setPlaceholderText(tr("radio.add_placeholder"))
        self.find_button = QPushButton(tr("radio.find"))
        self.find_button.setObjectName("primary")
        self.find_button.setDefault(True)
        self.find_button.clicked.connect(self._find)
        self.url.returnPressed.connect(self._find)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.url, 1)
        row.addWidget(self.find_button)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")

        self.icon_label = QLabel()
        self.icon_label.setObjectName("stationIcon")
        self.icon_label.setFixedSize(52, 52)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.name = QLineEdit()
        self.stream_label = ElidedLabel()
        self.stream_label.setObjectName("stationMeta")
        self.detail_label = QLabel()
        self.detail_label.setObjectName("muted")
        name_caption = QLabel(tr("radio.name").upper())
        name_caption.setObjectName("muted")
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(name_caption)
        texts.addWidget(self.name)
        texts.addWidget(self.stream_label)
        texts.addWidget(self.detail_label)
        found_row = QHBoxLayout()
        found_row.setSpacing(14)
        found_row.addWidget(self.icon_label, 0, Qt.AlignTop)
        found_row.addLayout(texts, 1)
        self.found_panel = QWidget()
        self.found_panel.setLayout(found_row)
        self.found_panel.hide()

        # a page whose player lists several stations: pick the ones to add
        self.many_caption = QLabel()
        self.many_caption.setWordWrap(True)
        self.many_list = QListWidget()
        self.many_list.setIconSize(QSize(36, 36))
        self.many_list.setMinimumHeight(190)
        self.many_list.itemChanged.connect(self._update_add_button)
        many_layout = QVBoxLayout()
        many_layout.setSpacing(8)
        many_layout.addWidget(self.many_caption)
        many_layout.addWidget(self.many_list)
        self.many_panel = QWidget()
        self.many_panel.setLayout(many_layout)
        self.many_panel.hide()

        self.add_button = QPushButton(tr("radio.add"))
        self.add_button.setObjectName("primary")
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton(tr("dialog.cancel"))
        self.cancel_button.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.add_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(prompt)
        layout.addLayout(row)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(self.found_panel)
        layout.addWidget(self.many_panel)
        layout.addSpacing(6)
        layout.addLayout(buttons)
        self.url.setFocus()

    # -- flow -------------------------------------------------------------------------------------------
    def _find(self) -> None:
        address = self.url.text().strip()
        if not address or self._worker is not None:
            return
        self._found = []
        self._address = address
        self.add_button.setEnabled(False)
        self.found_panel.hide()
        self.many_panel.hide()
        self.url.setEnabled(False)
        self.find_button.setEnabled(False)
        self.progress.show()
        self._set_status(tr("radio.searching"))
        resolver = self._resolver

        async def look(_progress):
            found = await resolver(address)
            found = [found] if isinstance(found, dict) else list(found)
            for entry in found:
                if entry.get("favicon"):
                    try:
                        await radio.fetch_icon(entry["favicon"])   # best effort: the icon is only decoration
                    except Exception:
                        pass
            return found

        worker = AsyncWorker(look, self)
        self._worker = worker
        worker.result.connect(self._on_found)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._search_over)
        worker.start()

    def _search_over(self) -> None:
        self.progress.hide()
        self.url.setEnabled(True)
        self.find_button.setEnabled(True)
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.setStyleSheet(f"color: {styles.RED};" if error else "")
        self.status.setText(text)

    def _icon_for(self, favicon: str):
        path = radio.icon_path(favicon) if favicon else None
        pixmap = QPixmap(str(path)) if path is not None and path.exists() else QPixmap()
        return pixmap.scaled(104, 104, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pixmap.isNull() else None

    @staticmethod
    def _detail(entry: dict) -> str:
        return " · ".join(str(p) for p in (entry.get("codec"), f"{entry['bitrate']} kbps" if entry.get("bitrate") else "",
                                           entry.get("tags")) if p)

    def _on_found(self, found: list) -> None:
        self._found = list(found)
        if len(found) == 1:
            entry = found[0]
            self.name.setText(entry.get("title") or "")
            self.stream_label.setText(entry["stream_url"])
            detail = self._detail(entry)
            self.detail_label.setText(detail)
            self.detail_label.setVisible(bool(detail))
            pixmap = self._icon_for(entry.get("favicon", ""))
            self.icon_label.setPixmap(pixmap if pixmap is not None else icons.glyph("radio", styles.SUBTEXT, 26))
            self._set_status(tr("radio.found"))
            self.found_panel.show()
            self.add_button.setText(tr("radio.add"))
            self.add_button.setEnabled(True)
        else:
            self.many_list.blockSignals(True)
            self.many_list.clear()
            for entry in found:
                item = QListWidgetItem((entry.get("title") or entry["stream_url"]) +
                                       (f"\n{self._detail(entry)}" if self._detail(entry) else ""))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                pixmap = self._icon_for(entry.get("favicon", ""))
                item.setIcon(QIcon(pixmap) if pixmap is not None else icons.icon("radio", styles.SUBTEXT, size=24))
                self.many_list.addItem(item)
            self.many_list.blockSignals(False)
            self.many_caption.setText(trn("radio.found_many", len(found)))
            self._set_status("")
            self.many_panel.show()
            self._update_add_button()
        self.add_button.setDefault(True)
        self.adjustSize()

    def _checked_indexes(self) -> list[int]:
        return [i for i in range(self.many_list.count()) if self.many_list.item(i).checkState() == Qt.Checked]

    def _update_add_button(self, *_args) -> None:
        checked = len(self._checked_indexes())
        self.add_button.setText(trn("radio.add_n", checked) if checked else tr("radio.add"))
        self.add_button.setEnabled(checked > 0)

    def _on_failed(self, message: str) -> None:
        if message == "cancelled":
            return
        code, _, detail = message.partition(": ")
        key = f"radio.err_{code}"
        text = tr(key, detail=detail) if code in ("bad_url", "unreachable", "no_audio") else tr("radio.err_unknown", detail=message)
        self._set_status(text, error=True)

    def reject(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(3000)
        super().reject()

    def _station_from(self, entry: dict, name: str = "") -> Station:
        try:
            given = normalize_url(self._address)
        except Exception:
            given = ""
        return Station(id=0, name=name or entry.get("title") or entry["stream_url"], stream_url=entry["stream_url"],
                       homepage=entry.get("homepage", ""), favicon=entry.get("favicon", ""), tags=entry.get("tags", ""),
                       codec=entry.get("codec", ""), bitrate=int(entry.get("bitrate") or 0),
                       source_url="" if given == entry["stream_url"] else given)

    def stations(self) -> list[Station]:
        """What to save: the one found (its name may have been edited), or the ticked ones of several."""
        if not self._found:
            return []
        if len(self._found) == 1:
            return [self._station_from(self._found[0], self.name.text().strip())]
        return [self._station_from(self._found[i]) for i in self._checked_indexes()]

    def station(self) -> Station | None:
        """The first station to save, or None if nothing was found."""
        chosen = self.stations()
        return chosen[0] if chosen else None
