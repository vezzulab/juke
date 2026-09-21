"""The "update available" prompt and the download progress window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser,
                               QVBoxLayout)

from .. import updater
from ..assets import ICON_SVG
from ..i18n import tr
from ..workers import AsyncWorker
from . import icons


class UpdateDialog(QDialog):
    """"You are on X. Do you want to update to Y?", with what is new and two answers: update or cancel.

    ``choice`` afterwards is "update" (download and install), "page" (open the release page when this
    install cannot replace itself), "later" (Cancel: ask again tomorrow) or "skip" (Cancel with the
    "don't ask again about this version" box ticked).
    """

    def __init__(self, release: updater.ReleaseInfo, current: str, can_update: bool, parent=None) -> None:
        super().__init__(parent)
        self.choice = "later"
        self.setWindowTitle(tr("update.title"))
        self.setMinimumWidth(540)

        picture = QLabel()
        picture.setPixmap(icons.render_svg(ICON_SVG.read_bytes(), 56))
        headline = QLabel(tr("update.question", version=release.version))
        headline.setObjectName("heading")
        headline.setWordWrap(True)
        current_label = QLabel(tr("update.current", current=current, version=release.version))
        current_label.setObjectName("muted")
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addWidget(headline)
        titles.addWidget(current_label)
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(picture, 0, Qt.AlignTop)
        head.addLayout(titles, 1)

        notes_title = QLabel(tr("update.notes_for", version=release.version).upper())
        notes_title.setObjectName("muted")
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMinimumHeight(190)
        if release.notes:
            self.notes.setMarkdown(release.notes[:8000])
        else:
            self.notes.setPlainText(tr("update.no_notes"))

        self.dont_ask = QCheckBox(tr("update.dont_ask"))
        self.cancel_button = QPushButton(tr("dialog.cancel"))
        self.primary_button = QPushButton(tr("update.accept") if can_update else tr("update.open_page"))
        self.primary_button.setObjectName("primary")
        self.primary_button.setDefault(True)
        self.cancel_button.clicked.connect(lambda: self._choose("skip" if self.dont_ask.isChecked() else "later"))
        self.primary_button.clicked.connect(lambda: self._choose("update" if can_update else "page"))
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.dont_ask)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.primary_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(head)
        layout.addSpacing(4)
        layout.addWidget(notes_title)
        layout.addWidget(self.notes, 1)
        layout.addSpacing(6)
        layout.addLayout(buttons)

    def reject(self) -> None:       # Esc or the window's close button is a Cancel
        self._choose("skip" if self.dont_ask.isChecked() else "later")

    def _choose(self, choice: str) -> None:
        self.choice = choice
        self.done(1 if choice in ("update", "page") else 0)


class DownloadDialog(QDialog):
    """Downloads the new AppImage with a progress bar. ``run()`` returns its path, or None."""

    def __init__(self, release: updater.ReleaseInfo, directory: Path, parent=None) -> None:
        super().__init__(parent)
        self.path: Path | None = None
        self.error = ""
        self._release, self._directory = release, directory
        self.setWindowTitle(tr("update.title"))
        self.setMinimumWidth(440)
        self.setModal(True)
        self.label = QLabel(tr("update.downloading", version=release.version))
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.cancel_button = QPushButton(tr("dialog.cancel"))
        self.cancel_button.clicked.connect(self._cancel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self._worker = AsyncWorker(lambda progress: updater.download_asset(release, directory, progress), self)
        self._worker.progress.connect(self.bar.setValue)
        self._worker.result.connect(self._done)
        self._worker.failed.connect(self._failed)

    def run(self) -> Path | None:
        self._worker.start()
        self.exec()
        self._worker.wait(5000)
        return self.path

    def _done(self, path) -> None:
        self.path = Path(path)
        self.accept()

    def _failed(self, message: str) -> None:
        self.error = "" if message == "cancelled" else message
        self.reject()

    def _cancel(self) -> None:
        self._worker.cancel()
        self.cancel_button.setEnabled(False)

    def reject(self) -> None:
        if self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        super().reject()
