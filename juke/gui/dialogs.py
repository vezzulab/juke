"""Small themed message boxes (Juke's own icon and plain text buttons)."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget

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


def ask_text(parent: QWidget | None, title: str, label: str, text: str = "") -> str | None:
    """Single-line text prompt; returns the trimmed text, or None if cancelled/empty."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(380)
    prompt = QLabel(label)
    field = QLineEdit(text)
    field.selectAll()
    buttons = QDialogButtonBox()
    ok = buttons.addButton(tr("dialog.ok"), QDialogButtonBox.AcceptRole)
    ok.setObjectName("primary")
    buttons.addButton(tr("dialog.cancel"), QDialogButtonBox.RejectRole)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    field.returnPressed.connect(dialog.accept)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(22, 20, 22, 18)
    layout.setSpacing(12)
    layout.addWidget(prompt)
    layout.addWidget(field)
    layout.addSpacing(4)
    layout.addWidget(buttons)
    field.setFocus()
    if not dialog.exec():
        return None
    return field.text().strip() or None
