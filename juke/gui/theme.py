"""Applies the dark / light theme to the whole application and follows the desktop when asked to."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QGuiApplication

from . import styles

CHOICES = ("auto", "dark", "light")


def system_scheme() -> str:
    """"light" or "dark" according to the desktop (Qt 6.5+); "dark" when it cannot tell."""
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
    except AttributeError:
        return "dark"
    return "light" if scheme == Qt.ColorScheme.Light else "dark"


def resolve(setting: str) -> str:
    return setting if setting in ("dark", "light") else system_scheme()


class ThemeManager(QObject):
    """One place that switches palette + stylesheet, then tells the widgets that cache colours."""

    def __init__(self, app, setting: str = "auto") -> None:
        super().__init__()
        self._app = app
        self.setting = setting if setting in CHOICES else "auto"
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):           # the desktop switched light/dark
            hints.colorSchemeChanged.connect(lambda *_: self.setting == "auto" and self.apply())

    @property
    def name(self) -> str:
        return styles.NAME

    def apply(self, setting: str | None = None) -> str:
        if setting is not None and setting in CHOICES:
            self.setting = setting
        name = resolve(self.setting)
        first = not getattr(self, "_applied", False)
        self._applied = True
        if name == styles.NAME and not first:
            return name
        styles.set_theme(name)
        self._app.setPalette(styles.build_palette())
        self._app.setStyleSheet(styles.build_stylesheet())
        styles.signals.changed.emit(name)
        return name
