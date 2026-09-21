"""Edit the tags and the cover of one song, or of a whole selection at once (written to the files and the library)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from ..db.database import Database, Track
from ..db.indexer import cover_key_for, cover_path, prepare_cover, save_cover, write_cover, write_tags
from ..i18n import tr
from .dialogs import notice

_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
_KEEP = object()        # the cover was not touched


def _shared(values):
    """The value every song has, or None when they differ."""
    first = values[0]
    return first if all(v == first for v in values) else None


class MetadataDialog(QDialog):
    """With several songs, a field left alone stays as it is in each of them; only what is typed is applied."""

    def __init__(self, tracks: Track | Sequence[Track], db: Database, parent=None) -> None:
        super().__init__(parent)
        self._tracks = [tracks] if isinstance(tracks, Track) else list(tracks)
        self._db = db
        self._cover: object = _KEEP                   # _KEEP, JPEG bytes, or None (take it out)
        many = len(self._tracks) > 1
        self.setWindowTitle(tr("meta.title_many", n=len(self._tracks)) if many else tr("meta.title"))
        self.setMinimumWidth(620)
        self.setAcceptDrops(True)

        def text_field(attr: str) -> QLineEdit:
            edit = QLineEdit()
            value = _shared([getattr(t, attr) for t in self._tracks])
            if value is None:
                edit.setPlaceholderText(tr("meta.multiple"))
            else:
                edit.setText(value)
            return edit

        def number_field(attr: str, top: int) -> QSpinBox:
            spin = QSpinBox()
            spin.setRange(0, top)
            spin.setSpecialValueText("—" if not many else tr("meta.multiple"))
            value = _shared([getattr(t, attr) for t in self._tracks])
            spin.setValue(value or 0)
            return spin

        self.title = text_field("title")
        self.artist = text_field("artist")
        self.album = text_field("album")
        self.genre = text_field("genre")
        self.year = number_field("year", 9999)
        self.number = number_field("track_no", 999)
        self._touched: set[str] = set()
        for name, widget in (("title", self.title), ("artist", self.artist), ("album", self.album), ("genre", self.genre)):
            widget.textEdited.connect(lambda _t, n=name: self._touched.add(n))
        self.year.valueChanged.connect(lambda _v: self._touched.add("year"))
        self.number.valueChanged.connect(lambda _v: self._touched.add("track_no"))
        if many:                                       # one title and one track number for many songs make no sense
            for widget in (self.title, self.number):
                widget.setEnabled(False)

        form = QFormLayout()
        form.setSpacing(10)
        for label, widget in (("meta.name", self.title), ("meta.artist", self.artist), ("meta.album", self.album),
                              ("meta.genre", self.genre), ("meta.year", self.year), ("meta.track", self.number)):
            form.addRow(tr(label), widget)

        self.art = QLabel()
        self.art.setObjectName("metaArt")
        self.art.setFixedSize(176, 176)
        self.art.setAlignment(Qt.AlignCenter)
        self.art.setWordWrap(True)
        self.choose = QPushButton(tr("meta.choose_cover"))
        self.choose.clicked.connect(self._pick_cover)
        self.remove = QPushButton(tr("meta.remove_cover"))
        self.remove.clicked.connect(self._remove_cover)
        side = QVBoxLayout()
        side.setSpacing(8)
        side.addWidget(self.art)
        side.addWidget(self.choose)
        side.addWidget(self.remove)
        side.addStretch(1)
        self._show_cover()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.Save).setText(tr("dialog.save"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("dialog.cancel"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        body = QHBoxLayout()
        body.setSpacing(22)
        body.addLayout(side)
        body.addLayout(form, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(16)
        layout.addLayout(body)
        layout.addWidget(buttons)

    # -- the cover ---------------------------------------------------------------------------------------
    def _show_cover(self) -> None:
        if self._cover is _KEEP:
            key = _shared([t.cover_key for t in self._tracks])
            pixmap = QPixmap(str(cover_path(key))) if key else QPixmap()
            mixed = key is None and any(t.cover_key for t in self._tracks)
        elif self._cover is None:
            pixmap, mixed = QPixmap(), False
        else:
            pixmap, mixed = QPixmap(), False
            pixmap.loadFromData(self._cover)
        if pixmap.isNull():
            self.art.setPixmap(QPixmap())
            self.art.setText(tr("meta.covers_differ") if mixed else tr("meta.no_cover"))
        else:
            self.art.setText("")
            self.art.setPixmap(pixmap.scaled(self.art.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.remove.setEnabled(not (self._cover is None or (self._cover is _KEEP and not any(t.cover_key for t in self._tracks))))

    def set_cover_from_file(self, path: str) -> bool:
        try:
            data = prepare_cover(Path(path).read_bytes())
        except OSError:
            data = None
        if data is None:
            notice(self, tr("meta.title"), tr("meta.bad_image"))
            return False
        self._cover = data
        self._show_cover()
        return True

    def _pick_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("meta.pick_title"), str(Path.home()), tr("meta.image_filter"))
        if path:
            self.set_cover_from_file(path)

    def _remove_cover(self) -> None:
        self._cover = None
        self._show_cover()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if any(u.isLocalFile() and u.toLocalFile().lower().endswith(_IMAGE_EXT) for u in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(_IMAGE_EXT):
                event.acceptProposedAction()
                self.set_cover_from_file(url.toLocalFile())
                return

    # -- saving ------------------------------------------------------------------------------------------
    def _changes(self) -> dict:
        fields: dict = {}
        for name, widget in (("title", self.title), ("artist", self.artist), ("album", self.album), ("genre", self.genre)):
            if name in self._touched:
                fields[name] = widget.text().strip()
        for name, widget in (("year", self.year), ("track_no", self.number)):
            if name in self._touched:
                fields[name] = widget.value()
        if "title" in fields and not fields["title"]:
            del fields["title"]                        # a song always keeps a title
        return fields

    def _save(self) -> None:
        fields = self._changes()
        failed: list[str] = []
        for track in self._tracks:
            row = dict(fields)
            if track.is_local and row:
                try:
                    write_tags(track.location, row)
                except Exception as exc:               # unsupported container, read-only file...
                    failed.append(f"{Path(track.location).name}: {exc}")
                    continue                           # nothing reached the file: the library stays as it was
            if self._cover is not _KEEP:
                if track.is_local:
                    try:
                        write_cover(track.location, self._cover)
                    except Exception as exc:           # the picture still lives in Juke, just not inside this file
                        failed.append(f"{Path(track.location).name}: {exc}")
                if self._cover is None:
                    row["cover_key"] = ""
                else:
                    key = cover_key_for(row.get("artist", track.artist), row.get("album", track.album), track.location)
                    if save_cover(key, self._cover):
                        row["cover_key"] = key
            if row:
                self._db.update_tags(track.id, **row)
        if failed:
            shown = "\n".join(failed[:6]) + ("\n…" if len(failed) > 6 else "")
            notice(self, tr("meta.title"), tr("meta.error", error=shown))
        self.accept()
