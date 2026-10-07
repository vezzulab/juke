"""Preferences: language, menu integration, music folders and the Airsonic server."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..api.airsonic import AirsonicClient, normalize_base_url
from ..config import Config
from ..i18n import LANGUAGES, tr
from ..workers import AsyncWorker
from . import styles
from .icons import theme_swatch


class SettingsDialog(QDialog):
    def __init__(self, config: Config, integration_installed: bool, parent=None, tab: int = 0) -> None:
        super().__init__(parent)
        self._config = config
        self._worker: AsyncWorker | None = None
        self._detected_auth: str | None = None
        self.setWindowTitle(tr("settings.title"))
        self.setMinimumSize(640, 540)

        self.tabs = tabs = QTabWidget()
        tabs.addTab(self._general_tab(integration_installed), tr("settings.general"))
        tabs.addTab(self._playback_tab(), tr("settings.playback"))
        tabs.addTab(self._library_tab(), tr("settings.library"))
        tabs.addTab(self._airsonic_tab(), tr("settings.airsonic"))
        tabs.setCurrentIndex(max(0, min(int(tab), tabs.count() - 1)))

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
    # Every tab is a column of blocks: a control, and under it a few words of explanation that wrap to the width of the
    # window. (A form with wrapping labels in one row squeezed the explanations over the controls.)
    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 20, 10, 10)
        layout.setSpacing(6)
        return page, layout

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("muted")
        label.setWordWrap(True)
        label.setContentsMargins(26, 0, 0, 0)          # lines up under the text of a check box
        return label

    @staticmethod
    def _gap(layout: QVBoxLayout, pixels: int = 14) -> None:
        layout.addSpacing(pixels)

    @staticmethod
    def _labelled(layout: QVBoxLayout, text: str, widget: QWidget) -> None:
        row = QHBoxLayout()
        row.setSpacing(14)
        caption = QLabel(text)
        caption.setMinimumWidth(190)
        row.addWidget(caption)
        row.addWidget(widget, 1)
        layout.addLayout(row)

    def _general_tab(self, integration_installed: bool) -> QWidget:
        page, layout = self._page()
        self.language = QComboBox()
        self.language.addItem(tr("settings.language_auto"), "auto")
        for code, (label, _) in LANGUAGES.items():
            self.language.addItem(label, code)
        self.language.setCurrentIndex(max(0, self.language.findData(self._config.get("language"))))
        self._labelled(layout, tr("settings.language"), self.language)
        self._gap(layout, 10)
        self.theme = QComboBox()
        names = {"auto": "settings.theme_auto", "dark": "settings.theme_dark", "light": "settings.theme_light"}
        for value in ("auto", "dark", "light", *styles.COLOR_THEMES):
            label = tr(names.get(value, f"theme.{value}"))
            if value == "auto":
                self.theme.addItem(label, value)
            else:
                self.theme.addItem(theme_swatch(value), label, value)
        self.theme.setCurrentIndex(max(0, self.theme.findData(self._config.get("theme"))))
        self._labelled(layout, tr("settings.theme"), self.theme)
        self._gap(layout, 22)
        self.updates = QCheckBox(tr("settings.updates"))
        self.updates.setChecked(bool(self._config.get("update.enabled")))
        layout.addWidget(self.updates)
        layout.addWidget(self._hint(tr("settings.updates_hint")))
        check_now = QPushButton(tr("menu.check_updates"))
        check_now.setCursor(Qt.PointingHandCursor)
        owner = self.parent()
        check_now.setEnabled(hasattr(owner, "check_for_updates"))
        if check_now.isEnabled():
            check_now.clicked.connect(lambda: owner.check_for_updates(manual=True))
        row = QHBoxLayout()
        row.addWidget(check_now)
        row.addStretch(1)
        layout.addLayout(row)
        self._gap(layout)
        self.integration = QCheckBox(tr("settings.integration"))
        self.integration.setChecked(integration_installed)
        layout.addWidget(self.integration)
        layout.addWidget(self._hint(tr("settings.integration_hint")))
        layout.addStretch(1)
        return page

    def _playback_tab(self) -> QWidget:
        page, layout = self._page()
        self.stay_awake = QCheckBox(tr("settings.stay_awake"))
        self.stay_awake.setChecked(bool(self._config.get("stay_awake")))
        layout.addWidget(self.stay_awake)
        layout.addWidget(self._hint(tr("settings.stay_awake_hint")))
        self._gap(layout, 22)
        self.follow_volume = QCheckBox(tr("settings.volume_follow"))
        self.follow_volume.setChecked(bool(self._config.get("volume_follows_system")))
        layout.addWidget(self.follow_volume)
        layout.addWidget(self._hint(tr("settings.volume_follow_hint")))
        self._gap(layout, 22)
        self.crossfade = QSpinBox()
        self.crossfade.setRange(0, 12)
        self.crossfade.setSuffix(" s")
        self.crossfade.setSpecialValueText(tr("settings.crossfade_off"))
        self.crossfade.setValue(int(self._config.get("crossfade") or 0))
        self.crossfade.setMinimumWidth(130)
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(QLabel(tr("settings.crossfade")))
        row.addWidget(self.crossfade)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self._hint(tr("settings.crossfade_hint")))
        self._gap(layout, 22)
        self.meter = QComboBox()
        for value, label in (("auto", "settings.meter_auto"), ("on", "settings.meter_on"), ("off", "settings.meter_off")):
            self.meter.addItem(tr(label), value)
        self.meter.setCurrentIndex(max(0, self.meter.findData(self._config.get("meter"))))
        self._labelled(layout, tr("settings.meter"), self.meter)
        layout.addWidget(self._hint(tr("settings.meter_hint")))
        layout.addStretch(1)
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
        layout.addSpacing(10)
        self.lyrics_auto = QCheckBox(tr("settings.lyrics_auto"))
        self.lyrics_auto.setChecked(bool(self._config.get("lyrics.auto_search")))
        layout.addWidget(self.lyrics_auto)
        layout.addWidget(self._hint(tr("settings.lyrics_auto_hint")))
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
                return await client.ping(), client.auth_mode
            finally:
                await client.aclose()

        def connected(outcome):
            version, mode = outcome
            self._detected_auth = mode
            secure = normalize_base_url(url).startswith("https://")
            if mode == "password":
                key = "settings.as_ok_password_https" if secure else "settings.as_ok_password_http"
                self._status(tr(key, version=version), ok=secure, error=not secure)
            else:
                self._status(tr("settings.as_ok", version=version), ok=True)

        self._worker = AsyncWorker(probe, self)
        self._worker.result.connect(connected)
        self._worker.failed.connect(lambda message: self._status(tr("settings.as_failed", error=message), error=True))
        self._worker.finished.connect(lambda: self.as_test.setEnabled(True))
        self._worker.start()

    def _status(self, text: str, *, ok: bool = False, error: bool = False) -> None:
        from . import styles

        color = styles.GREEN if ok else styles.RED if error else styles.SUBTEXT
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
        config.set("theme", self.theme.currentData())
        config.set("meter", self.meter.currentData())
        config.set("crossfade", self.crossfade.value())
        config.set("stay_awake", self.stay_awake.isChecked())
        config.set("volume_follows_system", self.follow_volume.isChecked())
        config.set("update.enabled", self.updates.isChecked())
        config.set("lyrics.auto_search", self.lyrics_auto.isChecked())
        config.set("airsonic", {
            "enabled": self.as_enabled.isChecked(), "url": normalize_base_url(self.as_url.text()),
            "username": self.as_user.text().strip(), "password": self.as_password.text(),
            "auth": self._detected_auth or "auto",   # unknown until a connection worked: negotiate again
        })

    @property
    def wants_integration(self) -> bool:
        return self.integration.isChecked()
