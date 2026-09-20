"""Preferences: language, menu integration, music folders and the Airsonic server."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from ..api.airsonic import AirsonicClient, normalize_base_url
from ..config import Config
from ..i18n import LANGUAGES, tr
from ..workers import AsyncWorker


class SettingsDialog(QDialog):
    def __init__(self, config: Config, integration_installed: bool, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._worker: AsyncWorker | None = None
        self.setWindowTitle(tr("settings.title"))
        self.setMinimumSize(560, 470)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(integration_installed), tr("settings.general"))
        tabs.addTab(self._library_tab(), tr("settings.library"))
        tabs.addTab(self._airsonic_tab(), tr("settings.airsonic"))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.Save).setText(tr("dialog.save"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("dialog.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(tabs, 1)
        layout.addWidget(buttons)

    # -- tabs ---------------------------------------------------------------------------------------
    def _general_tab(self, integration_installed: bool) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(6, 18, 6, 6)
        form.setSpacing(14)
        self.language = QComboBox()
        self.language.addItem(tr("settings.language_auto"), "auto")
        for code, (label, _) in LANGUAGES.items():
            self.language.addItem(label, code)
        self.language.setCurrentIndex(max(0, self.language.findData(self._config.get("language"))))
        form.addRow(tr("settings.language"), self.language)
        self.integration = QCheckBox(tr("settings.integration"))
        self.integration.setChecked(integration_installed)
        form.addRow("", self.integration)
        hint = QLabel(tr("settings.integration_hint"))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        form.addRow("", hint)
        return page

    def _library_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 18, 6, 6)
        layout.setSpacing(10)
        layout.addWidget(QLabel(tr("settings.folders")))
        self.folders = QListWidget()
        self.folders.addItems(self._config.get("music_dirs", []))
        layout.addWidget(self.folders, 1)
        row = QHBoxLayout()
        add, remove = QPushButton(tr("settings.add_folder")), QPushButton(tr("settings.remove_folder"))
        add.clicked.connect(self._add_folder)
        remove.clicked.connect(lambda: [self.folders.takeItem(self.folders.row(i)) for i in self.folders.selectedItems()])
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)
        self.scan_on_start = QCheckBox(tr("settings.scan_on_start"))
        self.scan_on_start.setChecked(bool(self._config.get("scan_on_start")))
        layout.addWidget(self.scan_on_start)
        return page

    def _airsonic_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(6, 18, 6, 6)
        form.setSpacing(12)
        cfg = self._config.get("airsonic")
        self.as_enabled = QCheckBox(tr("settings.as_enable"))
        self.as_enabled.setChecked(bool(cfg["enabled"]))
        self.as_url = QLineEdit(cfg["url"])
        self.as_url.setPlaceholderText("https://music.example.com")
        self.as_user = QLineEdit(cfg["username"])
        self.as_password = QLineEdit(cfg["password"])
        self.as_password.setEchoMode(QLineEdit.Password)
        self.as_test = QPushButton(tr("settings.as_test"))
        self.as_test.clicked.connect(self._test_connection)
        self.as_status = QLabel("")
        self.as_status.setWordWrap(True)
        form.addRow("", self.as_enabled)
        form.addRow(tr("settings.as_url"), self.as_url)
        form.addRow(tr("settings.as_user"), self.as_user)
        form.addRow(tr("settings.as_password"), self.as_password)
        row = QHBoxLayout()
        row.addWidget(self.as_test)
        row.addWidget(self.as_status, 1)
        form.addRow("", row)
        note = QLabel(tr("settings.as_note"))
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow("", note)
        return page

    # -- actions ---------------------------------------------------------------------------------------
    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("settings.add_folder"))
        if folder and folder not in self.folder_list():
            self.folders.addItem(folder)

    def folder_list(self) -> list[str]:
        return [self.folders.item(i).text() for i in range(self.folders.count())]

    def _test_connection(self) -> None:
        url, user, password = self.as_url.text(), self.as_user.text(), self.as_password.text()
        if not (normalize_base_url(url) and user):
            self._status(tr("settings.as_missing"), error=True)
            return
        self.as_test.setEnabled(False)
        self._status(tr("settings.as_testing"))

        async def probe(_progress):
            client = AirsonicClient(url, user, password, timeout=10)
            try:
                return await client.ping()
            finally:
                await client.aclose()

        self._worker = AsyncWorker(probe, self)
        self._worker.result.connect(lambda version: self._status(tr("settings.as_ok", version=version), ok=True))
        self._worker.failed.connect(lambda message: self._status(tr("settings.as_failed", error=message), error=True))
        self._worker.finished.connect(lambda: self.as_test.setEnabled(True))
        self._worker.start()

    def _status(self, text: str, *, ok: bool = False, error: bool = False) -> None:
        color = "#a6e3a1" if ok else "#f38ba8" if error else "#9399b2"
        self.as_status.setStyleSheet(f"color: {color};")
        self.as_status.setText(text)

    def done(self, result: int) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        super().done(result)

    # -- result -----------------------------------------------------------------------------------------
    def apply_to(self, config: Config) -> None:
        config.set("language", self.language.currentData())
        config.set("music_dirs", self.folder_list())
        config.set("scan_on_start", self.scan_on_start.isChecked())
        config.set("airsonic", {
            "enabled": self.as_enabled.isChecked(), "url": normalize_base_url(self.as_url.text()),
            "username": self.as_user.text().strip(), "password": self.as_password.text(),
        })

    @property
    def wants_integration(self) -> bool:
        return self.integration.isChecked()
