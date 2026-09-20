"""Small reusable widgets: elided label, click-to-jump slider, time formatting."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QLabel, QSizePolicy, QSlider, QStyle


def format_time(ms: float) -> str:
    seconds = max(0, int(ms // 1000))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def format_duration(seconds: float) -> str:
    return format_time(seconds * 1000) if seconds > 0 else ""


class ElidedLabel(QLabel):
    """Single-line label that shows "…" instead of growing the layout."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.width())
        self.style().drawItemText(painter, self.rect(), int(self.alignment()), self.palette(),
                                  self.isEnabled(), text, QPalette.WindowText)


class JumpSlider(QSlider):
    """Horizontal slider whose groove jumps to the clicked position."""

    released_at = Signal(int)  # value after the user lets go

    def __init__(self, minimum: int = 0, maximum: int = 100, parent=None) -> None:
        super().__init__(Qt.Horizontal, parent)
        self.setRange(minimum, maximum)
        self.setCursor(Qt.PointingHandCursor)
        self.dragging = False

    def _value_at(self, x: float) -> int:
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(x), max(1, self.width()))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.setValue(self._value_at(event.position().x()))
            self.sliderMoved.emit(self.value())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.dragging:
            self.setValue(self._value_at(event.position().x()))
            self.sliderMoved.emit(self.value())
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.dragging and event.button() == Qt.LeftButton:
            self.dragging = False
            self.released_at.emit(self.value())
            event.accept()
