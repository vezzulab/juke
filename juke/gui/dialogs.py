"""Small themed message boxes (Juke's own icon and plain text buttons)."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from ..assets import ICON_SVG
from ..i18n import tr
from . import icons


def _box(parent: QWidget | None, title: str, text: str) -> QMessageBox:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIconPixmap(icons.render_svg(ICON_SVG.read_bytes(), 56))
    return box


def notice(parent: QWidget | None, title: str, text: str) -> None:
    box = _box(parent, title, text)
    ok = box.addButton(tr("dialog.ok"), QMessageBox.AcceptRole)
    ok.setObjectName("primary")
    box.exec()


def confirm(parent: QWidget | None, title: str, text: str) -> bool:
    box = _box(parent, title, text)
    yes = box.addButton(tr("dialog.yes"), QMessageBox.YesRole)
    yes.setObjectName("primary")
    box.addButton(tr("dialog.no"), QMessageBox.NoRole)
    box.setDefaultButton(yes)
    box.exec()
    return box.clickedButton() is yes
