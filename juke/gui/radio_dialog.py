"""Add a radio station by pasting any web address; Juke works out where the audio is."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ..api import radio
from ..api.radio_resolver import resolve_stream_url
from ..db.database import Station
from ..i18n import tr
from ..workers import AsyncWorker
from . import icons, styles
from .components.widgets import ElidedLabel


class AddStationDialog(QDialog):
    def __init__(self, parent=None, resolver=None) -> None:
        super().__init__(parent)
        self._resolver = resolver or resolve_stream_url
        self._found: dict | None = None
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
        layout.addSpacing(6)
        layout.addLayout(buttons)
        self.url.setFocus()

    # -- flow -------------------------------------------------------------------------------------------
    def _find(self) -> None:
        address = self.url.text().strip()
        if not address or self._worker is not None:
            return
        self._found = None
        self._address = address
        self.add_button.setEnabled(False)
        self.found_panel.hide()
        self.url.setEnabled(False)
        self.find_button.setEnabled(False)
        self.progress.show()
        self._set_status(tr("radio.searching"))
        resolver = self._resolver

        async def look(_progress):
            found = await resolver(address)
            if found.get("favicon"):
                try:
                    await radio.fetch_icon(found["favicon"])       # best effort: the icon is only decoration
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

    def _on_found(self, found: dict) -> None:
        self._found = found
        self.name.setText(found.get("title") or "")
        self.stream_label.setText(found["stream_url"])
        detail = " · ".join(str(p) for p in (found.get("codec"), f"{found['bitrate']} kbps" if found.get("bitrate") else "",
                                              found.get("tags")) if p)
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))
        favicon = found.get("favicon", "")
        pixmap = QPixmap(str(radio.icon_path(favicon))) if favicon and radio.icon_path(favicon).exists() else QPixmap()
        self.icon_label.setPixmap(pixmap.scaled(104, 104, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pixmap.isNull()
                                  else icons.glyph("radio", styles.SUBTEXT, 26))
        self._set_status(tr("radio.found"))
        self.found_panel.show()
        self.add_button.setEnabled(True)
        self.add_button.setDefault(True)
        self.adjustSize()

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

    def station(self) -> Station | None:
        """The station to save (name may have been edited), or None if nothing was found."""
        if not self._found:
            return None
        found = self._found
        from ..api.radio_resolver import normalize_url

        try:
            given = normalize_url(self._address)
        except Exception:
            given = ""
        return Station(id=0, name=self.name.text().strip() or found.get("title") or found["stream_url"],
                       stream_url=found["stream_url"], homepage=found.get("homepage", ""), favicon=found.get("favicon", ""),
                       tags=found.get("tags", ""), codec=found.get("codec", ""), bitrate=int(found.get("bitrate") or 0),
                       source_url="" if given == found["stream_url"] else given)
