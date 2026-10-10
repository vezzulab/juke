"""Top bar: transport, LCD display (art, title, seek bar, spectrum) and volume/EQ."""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QStackedWidget, QToolButton, QVBoxLayout,
                               QWidget)

from ...db.database import Station, Track
from ...i18n import tr
from .. import icons, styles
from .widgets import ElidedLabel, JumpSlider, format_time


class SpectrumWidget(QWidget):
    """Level meter. It is decorative: libVLC exposes no FFT data, so the bars follow a smooth
    synthetic pattern. Animation is the most expensive thing Juke does, so it only runs while
    audio plays, the window is in front and the user allows it (see Settings ▸ Level meter);
    otherwise a still, calm version is drawn and no timer runs at all."""

    BARS = 30
    FPS = 15

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(120, 38)
        self._levels = [0.0] * self.BARS
        self._t = 0.0
        self._playing = False
        self._allowed = True
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.CoarseTimer)
        self._timer.setInterval(1000 // self.FPS)
        self._timer.timeout.connect(self._tick)

    def set_active(self, playing: bool) -> None:
        self._playing = playing
        self._refresh_timer()

    def set_animation_allowed(self, allowed: bool) -> None:
        self._allowed = allowed
        self._refresh_timer()

    def _target(self, i: int) -> float:
        if not self._playing:
            return 0.0
        if self._allowed:
            wobble = 0.5 + 0.5 * math.sin(self._t * (2.3 + i * 0.29) + i * 1.7)
            swell = 0.55 + 0.45 * math.sin(self._t * 0.8 + i * 0.45) ** 2
            return (0.18 + 0.82 * wobble * swell) * (1.0 - 0.5 * i / self.BARS)
        # still picture while playing: a gentle fixed profile, no CPU
        return (0.22 + 0.18 * math.sin(i * 0.9) ** 2) * (1.0 - 0.4 * i / self.BARS)

    def _settled(self) -> bool:
        return all(abs(level - self._target(i)) < 0.01 for i, level in enumerate(self._levels))

    def _refresh_timer(self) -> None:
        if not self.isVisible():
            self._timer.stop()                 # nothing on screen: nothing to redraw, ever
            return
        animating = self._playing and self._allowed
        if animating or not self._settled():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_timer()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self) -> None:
        self._t += 1.0 / self.FPS
        for i in range(self.BARS):
            target = self._target(i)
            rate = 0.45 if target > self._levels[i] else 0.2
            self._levels[i] += (target - self._levels[i]) * rate
        self.update()
        if not (self._playing and self._allowed) and self._settled():
            self._timer.stop()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        gap = 3.0
        bar = max(2.0, (width - gap * (self.BARS - 1)) / self.BARS)
        gradient = QLinearGradient(0, 0, width, 0)
        gradient.setColorAt(0, QColor(styles.LCD_INK))
        gradient.setColorAt(1, QColor(styles.LCD_INK_SOFT))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        for i, level in enumerate(self._levels):
            bar_height = max(3.0, level * height)
            painter.setOpacity(0.35 + 0.65 * level)
            painter.drawRoundedRect(QRectF(i * (bar + gap), height - bar_height, bar, bar_height), bar / 2, bar / 2)


class LiveBadge(QWidget):
    """The red "● LIVE" pill shown while a radio station plays."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(58, 20)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        red = QColor(styles.RED)
        rect = QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -0.6)
        fill = QColor(red)
        fill.setAlpha(34)
        painter.setPen(QPen(red, 1.2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(red)
        painter.drawEllipse(QRectF(9, rect.center().y() - 3, 6, 6))
        font = QFont(self.font())
        font.setPixelSize(10)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.1)
        painter.setFont(font)
        painter.setPen(red)
        painter.drawText(QRectF(19, 0, self.width() - 22, self.height()), Qt.AlignVCenter | Qt.AlignLeft, tr("radio.live"))


class LcdDisplay(QFrame):
    """Retro-modern "LCD": cover, title, artist — album, spectrum and seek bar."""

    seek_requested = Signal(float)

    COVER = 64

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("lcd")
        self.setFixedHeight(104)
        self.setMinimumWidth(440)
        self._length_ms = 0
        self._track: Track | None = None
        self._station: Station | None = None
        self._connecting = False
        self._cover: QPixmap | None = None

        self.cover = QLabel()
        self.cover.setObjectName("cover")
        self.cover.setFixedSize(self.COVER, self.COVER)
        self.cover.setAlignment(Qt.AlignCenter)

        self.title = ElidedLabel()
        self.title.setObjectName("lcdTitle")
        self.subtitle = ElidedLabel()
        self.subtitle.setObjectName("lcdSub")
        self.next_up = ElidedLabel()                    # the song that comes after this one
        self.next_up.setObjectName("lcdNext")
        self.spectrum = SpectrumWidget()
        self.spectrum.setFixedWidth(150)

        self.elapsed = QLabel("0:00")
        self.elapsed.setObjectName("lcdTime")
        self.elapsed.setMinimumWidth(44)
        self.remaining = QLabel("-:--")
        self.remaining.setObjectName("lcdTime")
        self.remaining.setMinimumWidth(48)
        self.remaining.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.live_badge = LiveBadge()
        self.live_info = QLabel()                       # what replaces the seek bar while a station plays
        self.live_info.setObjectName("lcdLive")
        self.live_info.setAlignment(Qt.AlignCenter)
        self.seek = JumpSlider(0, 1000)
        self.seek.setObjectName("seek")
        self.seek.setEnabled(False)
        self.seek.sliderMoved.connect(self._scrub)
        self.seek.released_at.connect(lambda v: self.seek_requested.emit(v / 1000))

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(self.live_badge, 0, Qt.AlignVCenter)
        title_row.addWidget(self.title, 1)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addLayout(title_row)
        text.addWidget(self.subtitle)
        text.addWidget(self.next_up)
        self.progress_stack = QStackedWidget()
        self.progress_stack.setFixedHeight(20)
        self.progress_stack.addWidget(self.seek)
        self.progress_stack.addWidget(self.live_info)
        head = QHBoxLayout()
        head.setSpacing(16)
        head.addLayout(text, 1)
        head.addWidget(self.spectrum, 0, Qt.AlignVCenter)
        timing = QHBoxLayout()
        timing.setSpacing(10)
        timing.addWidget(self.elapsed)
        timing.addWidget(self.progress_stack, 1)
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

    def paintEvent(self, event) -> None:  # noqa: N802
        """A recessed bezel, an amber backlight and a pane of glass over it, like the window of a real player."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        ink = QColor(styles.LCD_INK)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#14110c"))                          # a thin dark rim, no more
        painter.drawRoundedRect(outer, 14, 14)
        window = outer.adjusted(1.5, 1.5, -1.5, -1.5)
        # An old incandescent / electroluminescent backlight: a warm, slightly uneven glow, brightest a little
        # above the middle, falling off into a brownish orange at the corners.
        centre = window.center()
        centre.setY(window.top() + window.height() * 0.42)
        light = QRadialGradient(centre, window.width() * 0.58)
        light.setColorAt(0, QColor(styles.LCD_LAMP))
        light.setColorAt(0.55, QColor(styles.LCD_LAMP_MID))
        light.setColorAt(1, QColor(styles.LCD_AMBER_EDGE))
        painter.setBrush(light)
        painter.drawRoundedRect(window, 12.5, 12.5)
        shade = QLinearGradient(0, window.top(), 0, window.bottom())  # the glass is deep: the edges darken
        shade.setColorAt(0, QColor(ink.red(), ink.green(), ink.blue(), 95))
        shade.setColorAt(0.2, QColor(ink.red(), ink.green(), ink.blue(), 0))
        shade.setColorAt(0.75, QColor(ink.red(), ink.green(), ink.blue(), 0))
        shade.setColorAt(1, QColor(ink.red(), ink.green(), ink.blue(), 85))
        painter.setBrush(shade)
        painter.drawRoundedRect(window, 12.5, 12.5)
        side = QLinearGradient(window.left(), 0, window.right(), 0)
        side.setColorAt(0, QColor(ink.red(), ink.green(), ink.blue(), 70))
        side.setColorAt(0.12, QColor(ink.red(), ink.green(), ink.blue(), 0))
        side.setColorAt(0.88, QColor(ink.red(), ink.green(), ink.blue(), 0))
        side.setColorAt(1, QColor(ink.red(), ink.green(), ink.blue(), 70))
        painter.setBrush(side)
        painter.drawRoundedRect(window, 12.5, 12.5)
        painter.setClipRect(window.adjusted(4, 3, -4, -3))            # the faint horizontal lines of an old panel
        painter.setPen(QPen(QColor(ink.red(), ink.green(), ink.blue(), 22), 1))
        for y in range(int(window.top()) + 3, int(window.bottom()), 3):
            painter.drawLine(int(window.left()), y, int(window.right()), y)
        painter.setClipping(False)
        glass = QLinearGradient(0, window.top(), 0, window.bottom())  # a soft reflection across the upper half
        glass.setColorAt(0, QColor(255, 244, 214, 58))
        glass.setColorAt(0.5, QColor(255, 244, 214, 12))
        glass.setColorAt(0.5001, QColor(255, 244, 214, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glass)
        painter.drawRoundedRect(window.adjusted(2, 2, -2, -2), 10.5, 10.5)

    def _scrub(self, value: int) -> None:
        if self._length_ms > 0:
            ms = self._length_ms * value / 1000
            self.elapsed.setText(format_time(ms))
            self.remaining.setText("-" + format_time(self._length_ms - ms))

    def _live_mode(self, on: bool) -> None:
        self.live_badge.setVisible(on)
        self.progress_stack.setCurrentIndex(1 if on else 0)
        if on:
            self.remaining.setText("")

    @staticmethod
    def _station_line(station: Station) -> str:
        quality = f"{station.codec} {station.bitrate} kbps" if station.codec and station.bitrate else station.codec
        return " · ".join(part for part in (quality, station.tags.split(",")[0].strip(), station.country) if part)

    def set_station(self, station: Station, cover: QPixmap | None) -> None:
        """Radio: LIVE badge, the station's name, and (via set_now_playing) the song on air."""
        self._track, self._station, self._cover = None, station, cover
        self._length_ms = 0
        self.title.setText(station.name)
        self.next_up.hide()
        self.subtitle.setText(tr("radio.connecting"))
        self._connecting = True
        self.live_info.setText(self._station_line(station) or tr("radio.streaming"))
        self._show_cover(cover)
        self.elapsed.setText("0:00")
        self.seek.setEnabled(False)
        self._live_mode(True)

    def set_next(self, text: str) -> None:
        self.next_up.setText(text)
        self.next_up.setVisible(bool(text) and self._station is None)

    def set_now_playing(self, text: str) -> None:
        self._connecting = False
        if self._station is not None:
            self.subtitle.setText(text or self._station_line(self._station) or tr("radio.streaming"))

    def clear(self) -> None:
        self._station = None
        self._live_mode(False)
        self._track = None
        self._length_ms = 0
        self.title.setText("Juke")
        self.next_up.hide()
        self.subtitle.setText(tr("lcd.idle"))
        self.cover.setPixmap(icons.placeholder_cover(self.COVER))
        self.elapsed.setText("0:00")
        self.remaining.setText("-:--")
        self.seek.setValue(0)
        self.seek.setEnabled(False)
        self.spectrum.set_active(False)

    def set_track(self, track: Track, cover: QPixmap | None) -> None:
        self._station = None
        self._live_mode(False)
        self._track = track
        self._cover = cover
        self.title.setText(track.title or tr("unknown_title"))
        artist = track.artist or tr("unknown_artist")
        self.subtitle.setText(f"{artist} — {track.album}" if track.album else artist)
        self._show_cover(cover)
        self._length_ms = int(track.duration * 1000)
        self.seek.setEnabled(True)

    def apply_theme(self) -> None:
        self.update()                            # the lamp changes colour with the theme
        self._show_cover(self._cover)            # the placeholder is drawn in theme colours

    def set_cover(self, cover: QPixmap | None) -> None:
        self._cover = cover
        self._show_cover(cover)

    def _show_cover(self, cover: QPixmap | None) -> None:
        if cover is None or cover.isNull():
            self.cover.setPixmap(icons.placeholder_cover(self.COVER, radio=self._station is not None))
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
        if self._station is not None:               # live: only the time on air, no seek bar
            self.elapsed.setText(format_time(elapsed_ms))
            if self._connecting and elapsed_ms > 0:  # audio is flowing: show the station's info until a title arrives
                self._connecting = False
                self.subtitle.setText(self._station_line(self._station) or tr("radio.streaming"))
            return
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
        if self._station is not None:
            self.live_badge.update()
            self.live_info.setText(self._station_line(self._station) or tr("radio.streaming"))
        elif self._track is None:
            self.subtitle.setText(tr("lcd.idle"))
        else:
            self.set_track(self._track, self._cover)


class CrossfadeLight(QAbstractButton):
    """The word "Crossfade" with a light beside it: green when the next song is brought in before this one ends, grey
    when it is off. A click turns it on or off."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._seconds = 0
        self.setCheckable(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setWeight(QFont.DemiBold)
        self.setFont(font)
        self.setFixedHeight(18)
        self.setFixedWidth(self.fontMetrics().horizontalAdvance("Crossfade") + 34)

    @property
    def on(self) -> bool:
        return self._seconds > 0

    def set_seconds(self, seconds: int) -> None:
        self._seconds = max(0, int(seconds))
        self.setToolTip(tr("tip.crossfade_on", n=self._seconds) if self.on else tr("tip.crossfade_off"))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        light = QColor(styles.GREEN if self.on else styles.MUTED)
        centre = QRectF(2, 2, 14, 14).center()
        if self.on:                                           # a soft glow round the green light
            glow = QColor(light)
            glow.setAlpha(60)
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(centre, 7.0, 7.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(light)
        painter.drawEllipse(centre, 4.2, 4.2)
        painter.setPen(QColor(styles.TEXT if self.on else styles.SUBTEXT))
        painter.setFont(self.font())
        painter.drawText(QRectF(22, 0, self.width() - 22, self.height()), Qt.AlignVCenter | Qt.AlignLeft, "Crossfade")


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
    crossfade_toggled = Signal(bool)

    REPEAT_CYCLE = ("off", "all", "one")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self._icon_specs: list[tuple[QToolButton, str, str, bool, int]] = []
        self._repeat = "off"
        self._state = "stopped"

        self.btn_prev = self._button("prev", 36)
        self.btn_play = self._button("play", 44, tone="accent", icon_size=22, name="play")
        self.btn_next = self._button("next", 36)
        self.btn_stop = self._button("stop", 36)
        self.btn_shuffle = self._button("shuffle", 34, checkable=True)
        self.btn_repeat = self._button("repeat", 34, checkable=True)
        self.lcd = LcdDisplay()
        self.btn_mute = self._button("volume", 34, checkable=False)
        self.volume = JumpSlider(0, 100)
        self.volume.setFixedWidth(112)
        self.btn_eq = self._button("eq", 36, checkable=True)
        self.crossfade = CrossfadeLight()
        self.crossfade.clicked.connect(lambda: self.crossfade_toggled.emit(not self.crossfade.on))

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
        volume_box = QVBoxLayout()                    # the volume, and under it whether crossfade is on
        volume_box.setSpacing(4)
        volume_row = QHBoxLayout()
        volume_row.setSpacing(6)
        volume_row.addWidget(self.btn_mute, 0, Qt.AlignVCenter)
        volume_row.addWidget(self.volume, 0, Qt.AlignVCenter)
        volume_box.addLayout(volume_row)
        volume_box.addWidget(self.crossfade, 0, Qt.AlignHCenter)
        layout.addLayout(volume_box)
        layout.addSpacing(6)
        layout.addWidget(self.btn_eq, 0, Qt.AlignVCenter)
        self.retranslate()

    @staticmethod
    def _tone(tone: str) -> str:
        return styles.ON_ACCENT if tone == "accent" else styles.TEXT

    def _button(self, glyph: str, side: int, *, checkable: bool = False, tone: str = "text",
                icon_size: int = 20, name: str | None = None) -> QToolButton:
        button = QToolButton()
        button.setFixedSize(side, side)
        button.setIconSize(QSize(icon_size, icon_size))
        button.setCheckable(checkable)
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.NoFocus)
        if name:
            button.setObjectName(name)
        button.setIcon(icons.icon(glyph, self._tone(tone), active=styles.ACCENT if checkable else None))
        self._icon_specs.append((button, glyph, tone, checkable, icon_size))
        return button

    def apply_theme(self) -> None:
        """Rebuild every icon in the new theme's colours."""
        for button, glyph, tone, checkable, _size in self._icon_specs:
            button.setIcon(icons.icon(glyph, self._tone(tone), active=styles.ACCENT if checkable else None))
        self.set_state(self._state)
        self.set_repeat(self._repeat)
        self._refresh_volume_icon()
        self.lcd.apply_theme()

    # -- state from the outside --------------------------------------------------------
    def set_state(self, state: str) -> None:
        self._state = state
        self.btn_play.setIcon(icons.icon("pause" if state == "playing" else "play", styles.ON_ACCENT, size=24))
        self.btn_play.setToolTip(tr("tip.pause") if state == "playing" else tr("tip.play"))
        self.lcd.spectrum.set_active(state == "playing")
        if state == "stopped":
            self.lcd.seek.setValue(0)
            self.lcd.elapsed.setText("0:00")

    def set_track(self, track: Track, cover: QPixmap | None) -> None:
        self.lcd.set_track(track, cover)

    def set_position(self, elapsed_ms: int, length_ms: int) -> None:
        self.lcd.set_position(elapsed_ms, length_ms)

    def set_station(self, station: Station, cover: QPixmap | None) -> None:
        self.lcd.set_station(station, cover)

    def set_now_playing(self, text: str) -> None:
        self.lcd.set_now_playing(text)

    def set_next(self, text: str) -> None:
        self.lcd.set_next(text)

    def set_crossfade(self, seconds: int) -> None:
        self.crossfade.set_seconds(seconds)

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

    def set_animating(self, allowed: bool) -> None:
        """Window in front and animation allowed? Otherwise the level meter stays still."""
        self.lcd.spectrum.set_animation_allowed(allowed)

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
        self.crossfade.set_seconds(self.crossfade._seconds)
        self.set_state(self._state)
        self.set_repeat(self._repeat)
        self._refresh_volume_icon()
        self.lcd.retranslate()
