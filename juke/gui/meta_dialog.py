"""Edit the tags of a local track (written to the file and to the library)."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QSpinBox, QVBoxLayout

from ..db.database import Database, Track
from ..db.indexer import write_tags
from ..i18n import tr
from .dialogs import notice


class MetadataDialog(QDialog):
    def __init__(self, track: Track, db: Database, parent=None) -> None:
        super().__init__(parent)
        self._track, self._db = track, db
        self.setWindowTitle(tr("meta.title"))
        self.setMinimumWidth(460)
        self.title = QLineEdit(track.title)
        self.artist = QLineEdit(track.artist)
        self.album = QLineEdit(track.album)
        self.genre = QLineEdit(track.genre)
        self.year = QSpinBox()
        self.year.setRange(0, 9999)
        self.year.setSpecialValueText("—")
        self.year.setValue(track.year)
        self.number = QSpinBox()
        self.number.setRange(0, 999)
        self.number.setSpecialValueText("—")
        self.number.setValue(track.track_no)

        form = QFormLayout()
        form.setSpacing(10)
        for label, widget in (("meta.name", self.title), ("meta.artist", self.artist), ("meta.album", self.album),
                              ("meta.genre", self.genre), ("meta.year", self.year), ("meta.track", self.number)):
            form.addRow(tr(label), widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.Save).setText(tr("dialog.save"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("dialog.cancel"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(16)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _save(self) -> None:
        fields = {
            "title": self.title.text().strip() or self._track.title,
            "artist": self.artist.text().strip(), "album": self.album.text().strip(),
            "genre": self.genre.text().strip(), "year": self.year.value(), "track_no": self.number.value(),
        }
        try:
            write_tags(self._track.location, fields)
        except Exception as exc:  # unsupported container, read-only file...
            notice(self, tr("meta.title"), tr("meta.error", error=str(exc)))
            return
        self._db.update_tags(self._track.id, **fields)
        self.accept()
