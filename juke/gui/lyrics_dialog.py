"""Add, edit and search for a song's lyrics."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from .. import lyrics as lyrics_lib
from ..db.database import Track
from ..i18n import tr
from ..workers import AsyncWorker
from .dialogs import notice


class LyricsEditDialog(QDialog):
    """Paste the lyrics or import a file. A ``.lrc`` file (lines with time stamps) makes them follow the song."""

    def __init__(self, track: Track, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("lyrics.edit_title"))
        self.resize(560, 520)
        head = QLabel(f"{track.title} — {track.artist}" if track.artist else track.title)
        head.setObjectName("heading")
        hint = QLabel(tr("lyrics.edit_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        self.editor = QPlainTextEdit(text)
        self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
        self.editor.setPlaceholderText(tr("lyrics.placeholder"))
        self.state = QLabel()
        self.state.setObjectName("muted")
        self.editor.textChanged.connect(self._state)
        load = QPushButton(tr("lyrics.import"))
        load.clicked.connect(self._import)
        clear = QPushButton(tr("lyrics.clear"))
        clear.clicked.connect(self.editor.clear)
        save = QPushButton(tr("dialog.save"))
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        cancel = QPushButton(tr("dialog.cancel"))
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(load)
        row.addWidget(clear)
        row.addWidget(self.state, 1)
        row.addWidget(cancel)
        row.addWidget(save)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        layout.addWidget(head)
        layout.addWidget(hint)
        layout.addWidget(self.editor, 1)
        layout.addLayout(row)
        self._state()

    def _state(self) -> None:
        text = self.editor.toPlainText()
        self.state.setText(tr("lyrics.synced") if lyrics_lib.is_synced(text) else "")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("lyrics.import"), str(Path.home()), tr("lyrics.file_filter"))
        if not path:
            return
        try:
            self.editor.setPlainText(Path(path).read_text(encoding="utf-8", errors="replace").strip())
        except OSError as exc:
            notice(self, tr("lyrics.edit_title"), str(exc))

    @property
    def text(self) -> str:
        return self.editor.toPlainText().strip()


class FindLyricsDialog(QDialog):
    """Search LRCLIB by title and artist, look at a result and use it."""

    def __init__(self, track: Track, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("lyrics.find_title"))
        self.resize(640, 560)
        self._found: list[lyrics_lib.Found] = []
        self._worker: AsyncWorker | None = None
        self.chosen = ""

        self.title = QLineEdit(track.title)
        self.artist = QLineEdit(track.artist)
        self.title.setPlaceholderText(tr("meta.name"))
        self.artist.setPlaceholderText(tr("meta.artist"))
        self.title.returnPressed.connect(self.search)
        self.artist.returnPressed.connect(self.search)
        self.go = QPushButton(tr("lyrics.search"))
        self.go.setObjectName("primary")
        self.go.clicked.connect(self.search)
        bar = QHBoxLayout()
        bar.addWidget(self.title, 2)
        bar.addWidget(self.artist, 1)
        bar.addWidget(self.go)

        self.status = QLabel(tr("lyrics.find_hint"))
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.results = QListWidget()
        self.results.setMaximumHeight(170)
        self.results.currentRowChanged.connect(self._preview)
        self.results.itemDoubleClicked.connect(lambda _i: self._use())
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.use = QPushButton(tr("lyrics.use"))
        self.use.setObjectName("primary")
        self.use.setEnabled(False)
        self.use.clicked.connect(self._use)
        cancel = QPushButton(tr("dialog.cancel"))
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.use)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        layout.addLayout(bar)
        layout.addWidget(self.status)
        layout.addWidget(self.results)
        layout.addWidget(self.view, 1)
        layout.addLayout(buttons)
        if track.title:
            self.search()

    def search(self) -> None:
        title, artist = self.title.text().strip(), self.artist.text().strip()
        if not title or (self._worker is not None and self._worker.isRunning()):
            return
        self.status.setText(tr("lyrics.searching"))
        self.results.clear()
        self.view.clear()
        self.use.setEnabled(False)
        worker = AsyncWorker(lambda _progress: lyrics_lib.search(title, artist), self)
        self._worker = worker
        worker.result.connect(self._show_results)
        worker.failed.connect(lambda message: self.status.setText(tr("lyrics.search_failed", error=message)))
        worker.finished.connect(lambda w=worker: (setattr(self, "_worker", None) if self._worker is w else None, w.deleteLater()))
        worker.start()

    def _show_results(self, found: list) -> None:
        self._found = found
        for item in found:
            minutes, seconds = divmod(int(item.duration), 60)
            badge = "  ·  " + tr("lyrics.synced_badge") if item.is_synced else ""
            line = f"{item.title} — {item.artist}" + (f"  ·  {item.album}" if item.album else "") + f"  ·  {minutes}:{seconds:02d}{badge}"
            self.results.addItem(QListWidgetItem(line))
        self.status.setText(tr("lyrics.results", n=len(found)) if found else tr("lyrics.no_results"))
        if found:
            self.results.setCurrentRow(0)

    def _preview(self, row: int) -> None:
        if 0 <= row < len(self._found):
            self.view.setPlainText(lyrics_lib.plain_text(self._found[row].text))
            self.use.setEnabled(True)

    def _use(self) -> None:
        row = self.results.currentRow()
        if 0 <= row < len(self._found):
            self.chosen = self._found[row].text
            self.accept()

    def done(self, code: int) -> None:  # noqa: N802
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(1500)
        super().done(code)
