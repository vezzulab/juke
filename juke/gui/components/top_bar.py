"""Top bar: transport, LCD display (art, title, seek bar, spectrum) and volume/EQ."""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget)

from ...db.database import Track
from ...i18n import tr
from .. import icons, styles
from .widgets import ElidedLabel, JumpSlider, format_time


class SpectrumWidget(QWidget):
    """Animated level meter. It is decorative: libVLC exposes no FFT data, so the
    bars follow a smooth synthetic pattern while audio is playing."""

    BARS = 30

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(120, 38)
        self._levels = [0.0] * self.BARS
        self._t = 0.0
        self._active = False
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def set_active(self, active: bool) -> None:
        self._active = active
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self) -> None:
        self._t += 0.033
        t = self._t
        peak = 0.0
        for i in range(self.BARS):
            if self._active:
                wobble = 0.5 + 0.5 * math.sin(t * (2.3 + i * 0.29) + i * 1.7)
                swell = 0.55 + 0.45 * math.sin(t * 0.8 + i * 0.45) ** 2
                target = (0.18 + 0.82 * wobble * swell) * (1.0 - 0.5 * i / self.BARS)
            else:
                target = 0.0
            rate = 0.4 if target > self._levels[i] else 0.14
            self._levels[i] += (target - self._levels[i]) * rate
            peak = max(peak, self._levels[i])
        self.update()
        if not self._active and peak < 0.01:
            self._timer.stop()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        gap = 3.0
        bar = max(2.0, (width - gap * (self.BARS - 1)) / self.BARS)
        gradient = QLinearGradient(0, 0, width, 0)
        gradient.setColorAt(0, QColor(styles.ACCENT))
        gradient.setColorAt(1, QColor(styles.ACCENT2))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        for i, level in enumerate(self._levels):
            bar_height = max(3.0, level * height)
            painter.setOpacity(0.35 + 0.65 * level)
            painter.drawRoundedRect(QRectF(i * (bar + gap), height - bar_height, bar, bar_height), bar / 2, bar / 2)


class LcdDisplay(QFrame):
    """Retro-modern "LCD": cover, title, artist — album, spectrum and seek bar."""

    seek_requested = Signal(float)

    COVER = 64

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("lcd")
        self.setFixedHeight(94)
        self.setMinimumWidth(440)
        self._length_ms = 0
        self._track: Track | None = None
        self._cover: QPixmap | None = None

        self.cover = QLabel()
        self.cover.setObjectName("cover")
        self.cover.setFixedSize(self.COVER, self.COVER)
        self.cover.setAlignment(Qt.AlignCenter)

        self.title = ElidedLabel()
        self.title.setObjectName("lcdTitle")
        self.subtitle = ElidedLabel()
        self.subtitle.setObjectName("lcdSub")
        self.spectrum = SpectrumWidget()
        self.spectrum.setFixedWidth(150)

        self.elapsed = QLabel("0:00")
        self.elapsed.setObjectName("lcdTime")
        self.elapsed.setMinimumWidth(44)
        self.remaining = QLabel("-:--")
        self.remaining.setObjectName("lcdTime")
        self.remaining.setMinimumWidth(48)
        self.remaining.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.seek = JumpSlider(0, 1000)
        self.seek.setObjectName("seek")
        self.seek.setEnabled(False)
        self.seek.sliderMoved.connect(self._scrub)
        self.seek.released_at.connect(lambda v: self.seek_requested.emit(v / 1000))

        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        head = QHBoxLayout()
        head.setSpacing(16)
        head.addLayout(text, 1)
        head.addWidget(self.spectrum, 0, Qt.AlignVCenter)
        timing = QHBoxLayout()
        timing.setSpacing(10)
        timing.addWidget(self.elapsed)
        timing.addWidget(self.seek, 1)
        timing.addWidget(self.remaining)
        column = QVBoxLayout()
        column.setSpacing(6)
        column.addLayout(head)
        column.addLayout(timing)
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 18, 12)
        root.setSpacing(14)
        root.addWidget(self.cover)
        root.addLayout(column, 1)
        self.clear()

    def _scrub(self, value: int) -> None:
        if self._length_ms > 0:
            ms = self._length_ms * value / 1000
            self.elapsed.setText(format_time(ms))
            self.remaining.setText("-" + format_time(self._length_ms - ms))

    def clear(self) -> None:
        self._track = None
        self._length_ms = 0
        self.title.setText("Juke")
        self.subtitle.setText(tr("lcd.idle"))
        self.cover.setPixmap(icons.placeholder_cover(self.COVER))
        self.elapsed.setText("0:00")
        self.remaining.setText("-:--")
        self.seek.setValue(0)
        self.seek.setEnabled(False)
        self.spectrum.set_active(False)

    def set_track(self, track: Track, cover: QPixmap | None) -> None:
        self._track = track
        self._cover = cover
        self.title.setText(track.title or tr("unknown_title"))
        artist = track.artist or tr("unknown_artist")
        self.subtitle.setText(f"{artist} — {track.album}" if track.album else artist)
        self._show_cover(cover)
        self._length_ms = int(track.duration * 1000)
        self.seek.setEnabled(True)

    def set_cover(self, cover: QPixmap | None) -> None:
        self._cover = cover
        self._show_cover(cover)

    def _show_cover(self, cover: QPixmap | None) -> None:
        if cover is None or cover.isNull():
            self.cover.setPixmap(icons.placeholder_cover(self.COVER))
            return
        dpr = self.devicePixelRatioF()
        side = int(self.COVER * dpr)
        scaled = cover.scaled(side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        scaled = scaled.copy((scaled.width() - side) // 2, (scaled.height() - side) // 2, side, side)
        scaled.setDevicePixelRatio(dpr)
        self.cover.setPixmap(scaled)

    def set_position(self, elapsed_ms: int, length_ms: int) -> None:
        if length_ms > 0:
            self._length_ms = length_ms
        if self.seek.dragging:
            return
        self.elapsed.setText(format_time(elapsed_ms))
        if self._length_ms > 0:
            self.remaining.setText("-" + format_time(self._length_ms - elapsed_ms))
            self.seek.setValue(int(1000 * min(elapsed_ms, self._length_ms) / self._length_ms))
        else:
            self.remaining.setText("-:--")
            self.seek.setValue(0)

    def retranslate(self) -> None:
        if self._track is None:
            self.subtitle.setText(tr("lcd.idle"))
        else:
            self.set_track(self._track, self._cover)


class TopBar(QWidget):
    prev_clicked = Signal()
    play_clicked = Signal()
    next_clicked = Signal()
    stop_clicked = Signal()
    seek_requested = Signal(float)
    volume_changed = Signal(int)
    mute_toggled = Signal(bool)
    eq_clicked = Signal()
    shuffle_toggled = Signal(bool)
    repeat_changed = Signal(str)

    REPEAT_CYCLE = ("off", "all", "one")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self._repeat = "off"
        self._state = "stopped"

        self.btn_prev = self._button("prev", 36)
        self.btn_play = self._button("play", 44, icon_color=styles.BASE, icon_size=22, name="play")
        self.btn_next = self._button("next", 36)
        self.btn_stop = self._button("stop", 36)
        self.btn_shuffle = self._button("shuffle", 34, checkable=True)
        self.btn_repeat = self._button("repeat", 34, checkable=True)
        self.lcd = LcdDisplay()
        self.btn_mute = self._button("volume", 34, checkable=False)
        self.volume = JumpSlider(0, 100)
        self.volume.setFixedWidth(112)
        self.btn_eq = self._button("eq", 36, checkable=True)

        self.btn_prev.clicked.connect(self.prev_clicked)
        self.btn_play.clicked.connect(self.play_clicked)
        self.btn_next.clicked.connect(self.next_clicked)
        self.btn_stop.clicked.connect(self.stop_clicked)
        self.btn_shuffle.toggled.connect(self.shuffle_toggled)
        self.btn_repeat.clicked.connect(self._cycle_repeat)
        self.btn_eq.clicked.connect(self.eq_clicked)
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.volume.valueChanged.connect(self._volume_moved)
        self.lcd.seek_requested.connect(self.seek_requested)
        self._muted = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(6)
        for widget in (self.btn_prev, self.btn_play, self.btn_next, self.btn_stop):
            layout.addWidget(widget, 0, Qt.AlignVCenter)
        layout.addSpacing(8)
        layout.addWidget(self.btn_shuffle, 0, Qt.AlignVCenter)
        layout.addWidget(self.btn_repeat, 0, Qt.AlignVCenter)
        layout.addSpacing(14)
        layout.addWidget(self.lcd, 1)
        layout.addSpacing(14)
        layout.addWidget(self.btn_mute, 0, Qt.AlignVCenter)
        layout.addWidget(self.volume, 0, Qt.AlignVCenter)
        layout.addSpacing(6)
        layout.addWidget(self.btn_eq, 0, Qt.AlignVCenter)
        self.retranslate()

    @staticmethod
    def _button(glyph: str, side: int, *, checkable: bool = False, icon_color: str = styles.TEXT,
                icon_size: int = 20, name: str | None = None) -> QToolButton:
        button = QToolButton()
        button.setFixedSize(side, side)
        button.setIconSize(QSize(icon_size, icon_size))
        button.setCheckable(checkable)
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.NoFocus)
        if name:
            button.setObjectName(name)
        button.setIcon(icons.icon(glyph, icon_color, active=styles.ACCENT if checkable else None))
        return button

    # -- state from the outside --------------------------------------------------------
    def set_state(self, state: str) -> None:
        self._state = state
        self.btn_play.setIcon(icons.icon("pause" if state == "playing" else "play", styles.BASE, size=24))
        self.btn_play.setToolTip(tr("tip.pause") if state == "playing" else tr("tip.play"))
        self.lcd.spectrum.set_active(state == "playing")
        if state == "stopped":
            self.lcd.seek.setValue(0)
            self.lcd.elapsed.setText("0:00")

    def set_track(self, track: Track, cover: QPixmap | None) -> None:
        self.lcd.set_track(track, cover)

    def set_position(self, elapsed_ms: int, length_ms: int) -> None:
        self.lcd.set_position(elapsed_ms, length_ms)

    def set_volume(self, volume: int, muted: bool) -> None:
        self.volume.blockSignals(True)
        self.volume.setValue(volume)
        self.volume.blockSignals(False)
        self._muted = muted
        self._refresh_volume_icon()

    def set_shuffle(self, enabled: bool) -> None:
        self.btn_shuffle.blockSignals(True)
        self.btn_shuffle.setChecked(enabled)
        self.btn_shuffle.blockSignals(False)

    def set_repeat(self, mode: str) -> None:
        self._repeat = mode if mode in self.REPEAT_CYCLE else "off"
        self.btn_repeat.setChecked(self._repeat != "off")
        self.btn_repeat.setIcon(icons.icon("repeat-one" if self._repeat == "one" else "repeat",
                                           styles.TEXT, active=styles.ACCENT))
        self.btn_repeat.setToolTip(tr(f"tip.repeat_{self._repeat}"))

    def set_eq_open(self, is_open: bool) -> None:
        self.btn_eq.setChecked(is_open)

    # -- interaction --------------------------------------------------------------------
    def _cycle_repeat(self) -> None:
        nxt = self.REPEAT_CYCLE[(self.REPEAT_CYCLE.index(self._repeat) + 1) % 3]
        self.set_repeat(nxt)
        self.repeat_changed.emit(nxt)

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        self._refresh_volume_icon()
        self.mute_toggled.emit(self._muted)

    def _volume_moved(self, value: int) -> None:
        if self._muted and value > 0:
            self._muted = False
            self.mute_toggled.emit(False)
        self._refresh_volume_icon()
        self.volume_changed.emit(value)

    def _refresh_volume_icon(self) -> None:
        silent = self._muted or self.volume.value() == 0
        self.btn_mute.setIcon(icons.icon("mute" if silent else "volume", styles.TEXT))
        self.btn_mute.setToolTip(tr("tip.unmute") if silent else tr("tip.mute"))

    def retranslate(self) -> None:
        self.btn_prev.setToolTip(tr("tip.previous"))
        self.btn_next.setToolTip(tr("tip.next"))
        self.btn_stop.setToolTip(tr("tip.stop"))
        self.btn_shuffle.setToolTip(tr("tip.shuffle"))
        self.btn_eq.setToolTip(tr("tip.equalizer"))
        self.set_state(self._state)
        self.set_repeat(self._repeat)
        self._refresh_volume_icon()
        self.lcd.retranslate()
