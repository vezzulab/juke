"""Floating equalizer window: 10-band graphic EQ, presets, preamp, speed and balance."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QSlider, QVBoxLayout, QWidget)

from ...audio.engine import AudioEngine
from ...audio.equalizer import BAND_GROUPS, BAND_LABELS, BANDS_HZ, MAX_DB, MIN_DB, Equalizer
from ...i18n import tr
from .. import styles
from ..dialogs import ask_text, notice
from .widgets import JumpSlider

SCALE = 10  # slider units per dB


class CurveWidget(QWidget):
    """Smooth response curve drawn through the ten band gains."""

    def __init__(self, equalizer: Equalizer, parent=None) -> None:
        super().__init__(parent)
        self._eq = equalizer
        self.setMinimumHeight(96)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad = 14.0
        painter.setPen(QPen(QColor(styles.BORDER), 1))
        painter.drawLine(QPointF(pad, h / 2), QPointF(w - pad, h / 2))
        gains = self._eq.gains
        limit = 12.0
        xs = [pad + (w - 2 * pad) * i / 9 for i in range(10)]
        total = [max(-limit, min(limit, g + self._eq.preamp)) for g in gains]
        ys = [h / 2 - (v / limit) * (h / 2 - 10) for v in total]
        path = QPainterPath(QPointF(xs[0], ys[0]))
        for i in range(9):  # Catmull-Rom -> cubic Bézier
            p0 = QPointF(xs[max(i - 1, 0)], ys[max(i - 1, 0)])
            p1, p2 = QPointF(xs[i], ys[i]), QPointF(xs[i + 1], ys[i + 1])
            p3 = QPointF(xs[min(i + 2, 9)], ys[min(i + 2, 9)])
            path.cubicTo(p1 + (p2 - p0) / 6, p2 - (p3 - p1) / 6, p2)
        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0, QColor(styles.ACCENT))
        gradient.setColorAt(1, QColor(styles.ACCENT2))
        fill = QPainterPath(path)
        fill.lineTo(xs[-1], h / 2)
        fill.lineTo(xs[0], h / 2)
        fill.closeSubpath()
        painter.setOpacity(0.14 if self._eq.enabled else 0.06)
        painter.fillPath(fill, gradient)
        painter.setOpacity(1.0 if self._eq.enabled else 0.4)
        painter.setPen(QPen(gradient, 2.4, Qt.SolidLine, Qt.RoundCap))
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(styles.TEXT))
        for x, y in zip(xs, ys):
            painter.drawEllipse(QPointF(x, y), 2.6, 2.6)


class EqualizerDialog(QDialog):
    closed = Signal()

    def __init__(self, equalizer: Equalizer, engine: AudioEngine, parent=None) -> None:
        super().__init__(parent)
        self._eq = equalizer
        self._engine = engine
        self.setMinimumWidth(860)

        self.enabled = QCheckBox()
        self.presets = QComboBox()
        self.presets.setMinimumWidth(190)
        self.btn_save = QPushButton()
        self.btn_delete = QPushButton()
        self.btn_reset = QPushButton()
        self.curve = CurveWidget(equalizer)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self.enabled)
        top.addStretch(1)
        top.addWidget(self.presets)
        top.addWidget(self.btn_save)
        top.addWidget(self.btn_delete)
        top.addWidget(self.btn_reset)

        self.preamp_slider = self._vertical_slider()
        self.preamp_value = self._value_label()
        self.preamp_name = QLabel()
        self.preamp_name.setObjectName("muted")
        self.hint = QLabel()
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.song_note = QLabel()                          # shown while the song that plays has an equalizer of its own
        self.song_note.setWordWrap(True)
        self.song_note.setObjectName("eqSongNote")
        self.song_back = QPushButton()
        self.song_back.clicked.connect(self._eq.clear_song)
        note = QHBoxLayout()
        note.addWidget(self.song_note, 1)
        note.addWidget(self.song_back)
        self.song_bar = QWidget()
        self.song_bar.setLayout(note)
        self.song_bar.hide()
        self.band_sliders: list[QSlider] = []
        self.band_values: list[QLabel] = []
        self.band_names: list[QLabel] = []         # "Deep bass", "Voice"...: what the bar changes, in plain words
        self.band_freqs: list[QLabel] = []
        self.group_labels: dict[str, QLabel] = {}

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        self._add_column(grid, 0, self.preamp_value, self.preamp_slider, self.preamp_name)
        divider = QWidget()
        divider.setFixedWidth(1)
        divider.setObjectName("eqDivider")
        grid.addWidget(divider, 0, 1, 5, 1)
        first_of: dict[str, int] = {}
        count_of: dict[str, int] = {}
        for i, label in enumerate(BAND_LABELS):
            slider, value = self._vertical_slider(), self._value_label()
            freq = QLabel(label)
            freq.setObjectName("muted")
            nick = QLabel()
            nick.setAlignment(Qt.AlignCenter)
            nick.setWordWrap(True)
            nick.setMinimumHeight(30)
            self.band_sliders.append(slider)
            self.band_values.append(value)
            self.band_freqs.append(freq)
            self.band_names.append(nick)
            self._add_column(grid, i + 2, value, slider, freq)
            grid.addWidget(nick, 3, i + 2, Qt.AlignHCenter | Qt.AlignTop)
            group = BAND_GROUPS[i]
            first_of.setdefault(group, i + 2)
            count_of[group] = count_of.get(group, 0) + 1
            slider.valueChanged.connect(lambda v, idx=i: self._eq.set_band(idx, v / SCALE))
        for group, column in first_of.items():          # BASS / MIDDLE / TREBLE over the bars they cover
            caption = QLabel()
            caption.setAlignment(Qt.AlignCenter)
            caption.setObjectName("eqGroup")
            self.group_labels[group] = caption
            grid.addWidget(caption, 4, column, 1, count_of[group])
        self.preamp_slider.valueChanged.connect(lambda v: self._eq.set_preamp(v / SCALE))

        self.extras = QGroupBox()
        extras = QGridLayout(self.extras)
        extras.setHorizontalSpacing(14)
        extras.setVerticalSpacing(10)
        self.speed_label = QLabel()
        self.speed = JumpSlider(50, 200)
        self.speed.setValue(int(round(engine.rate * 100)))
        self.speed_value = QLabel()
        self.speed_value.setMinimumWidth(58)
        self.speed_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.speed_reset = QPushButton()
        self.balance_label = QLabel()
        self.balance = JumpSlider(-100, 100)
        self.balance.setValue(int(round(engine.balance * 100)))
        self.balance_value = QLabel()
        self.balance_value.setMinimumWidth(58)
        self.balance_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.balance_reset = QPushButton()
        for row, (label, slider, value, reset) in enumerate((
                (self.speed_label, self.speed, self.speed_value, self.speed_reset),
                (self.balance_label, self.balance, self.balance_value, self.balance_reset))):
            extras.addWidget(label, row, 0)
            extras.addWidget(slider, row, 1)
            extras.addWidget(value, row, 2)
            extras.addWidget(reset, row, 3)
        extras.setColumnStretch(1, 1)
        self.balance.setEnabled(engine.balance_supported)
        self.balance_reset.setEnabled(engine.balance_supported)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        layout.addLayout(top)
        layout.addWidget(self.song_bar)
        layout.addWidget(self.hint)
        layout.addWidget(self.curve)
        layout.addLayout(grid)
        layout.addWidget(self.extras)

        self.enabled.toggled.connect(self._eq.set_enabled)
        self.presets.activated.connect(self._preset_chosen)
        self.btn_save.clicked.connect(self._save_preset)
        self.btn_delete.clicked.connect(self._delete_preset)
        self.btn_reset.clicked.connect(self._eq.reset)
        self.speed.valueChanged.connect(self._speed_changed)
        self.speed_reset.clicked.connect(lambda: self.speed.setValue(100))
        self.balance.valueChanged.connect(self._balance_changed)
        self.balance_reset.clicked.connect(lambda: self.balance.setValue(0))
        self._eq.changed.connect(self._sync)

        self.retranslate()
        self._sync()
        self._speed_changed(self.speed.value())
        self._balance_changed(self.balance.value())

    # -- construction helpers ---------------------------------------------------------------
    @staticmethod
    def _vertical_slider() -> QSlider:
        slider = QSlider(Qt.Vertical)
        slider.setRange(int(MIN_DB * SCALE), int(MAX_DB * SCALE))
        slider.setPageStep(5 * SCALE)
        slider.setSingleStep(SCALE // 2)
        slider.setMinimumHeight(170)
        slider.setCursor(Qt.PointingHandCursor)
        return slider

    @staticmethod
    def _value_label() -> QLabel:
        label = QLabel("0.0")
        label.setAlignment(Qt.AlignCenter)
        label.setObjectName("eqValue")
        return label

    @staticmethod
    def _add_column(grid: QGridLayout, column: int, value: QLabel, slider: QSlider, name: QLabel) -> None:
        name.setAlignment(Qt.AlignCenter)
        grid.addWidget(value, 0, column, Qt.AlignHCenter)
        grid.addWidget(slider, 1, column, Qt.AlignHCenter)
        grid.addWidget(name, 2, column, Qt.AlignHCenter)
        grid.setColumnStretch(column, 1)

    # -- state ---------------------------------------------------------------------------------------
    def _sync(self) -> None:
        """Mirror the Equalizer object into every widget without feeding changes back."""
        eq = self._eq
        for widget in (self.enabled, self.presets, self.preamp_slider, *self.band_sliders):
            widget.blockSignals(True)
        self.enabled.setChecked(eq.enabled)
        self.preamp_slider.setValue(round(eq.preamp * SCALE))
        self.preamp_value.setText(f"{eq.preamp:+.1f}")
        for slider, label, gain in zip(self.band_sliders, self.band_values, eq.gains):
            slider.setValue(round(gain * SCALE))
            label.setText(f"{gain:+.1f}")
        self.presets.clear()
        if eq.preset is None:
            self.presets.addItem(tr("eq.custom"), None)
        for name in eq.preset_names():
            self.presets.addItem(tr("eq.preset." + name) if eq.is_builtin(name) else name, name)
        self.presets.setCurrentIndex(max(0, self.presets.findData(eq.preset)) if eq.preset else 0)
        for widget in (self.enabled, self.presets, self.preamp_slider, *self.band_sliders):
            widget.blockSignals(False)
        own = eq.song_id is not None
        self.song_bar.setVisible(own)
        self.enabled.setEnabled(not own)                    # a song with its own curve is always shaped by it
        if own:
            self.song_note.setText(tr("eq.song_note", name=eq.preset or tr("eq.custom")))
        controls_on = eq.enabled
        for slider in (self.preamp_slider, *self.band_sliders):
            slider.setEnabled(controls_on)
        self.btn_delete.setEnabled(eq.preset in eq.custom)
        self.curve.update()

    def _preset_chosen(self, index: int) -> None:
        name = self.presets.itemData(index)
        if name:
            if not self._eq.enabled:
                self._eq.set_enabled(True)
            self._eq.load_preset(name)

    def _save_preset(self) -> None:
        name = ask_text(self, tr("eq.save_title"), tr("eq.save_prompt"))
        if not name:
            return
        if not self._eq.save_custom(name):
            notice(self, tr("eq.save_title"), tr("eq.name_reserved"))

    def _delete_preset(self) -> None:
        if self._eq.preset in self._eq.custom:
            self._eq.delete_custom(self._eq.preset)

    def _speed_changed(self, value: int) -> None:
        rate = round(value / 5) * 5 / 100
        self._engine.set_rate(rate)
        self.speed_value.setText(f"{rate:.2f}×")

    def _balance_changed(self, value: int) -> None:
        self._engine.set_balance(value / 100)
        if value == 0:
            self.balance_value.setText(tr("eq.center"))
        else:
            self.balance_value.setText(f"{tr('eq.left') if value < 0 else tr('eq.right')} {abs(value)}")

    def retranslate(self) -> None:
        self.setWindowTitle(tr("eq.title"))
        self.enabled.setText(tr("eq.enable"))
        self.btn_save.setText(tr("eq.save"))
        self.btn_delete.setText(tr("eq.delete"))
        self.btn_reset.setText(tr("eq.reset"))
        self.song_back.setText(tr("eq.song_back"))
        self.preamp_name.setText(tr("eq.preamp_short"))
        self.hint.setText(tr("eq.hint"))
        for i, hz in enumerate(BANDS_HZ):
            about = f"<b>{tr(f'eq.band.{hz}.name')}</b> · {BAND_LABELS[i]} Hz<br>{tr(f'eq.band.{hz}.about')}"
            self.band_names[i].setText(tr(f"eq.band.{hz}.name"))
            self.band_freqs[i].setText(f"{hz} Hz" if hz < 1000 else f"{hz / 1000:g} kHz")
            for widget in (self.band_sliders[i], self.band_names[i], self.band_freqs[i], self.band_values[i]):
                widget.setToolTip(about)
        for group, caption in self.group_labels.items():
            caption.setText(tr(f"eq.group.{group}"))
        for widget in (self.preamp_slider, self.preamp_name, self.preamp_value):
            widget.setToolTip(f"<b>{tr('eq.preamp')}</b><br>{tr('eq.preamp.about')}")
        self.extras.setTitle(tr("eq.extras"))
        self.speed_label.setText(tr("eq.speed"))
        self.balance_label.setText(tr("eq.balance"))
        self.speed_reset.setText(tr("eq.reset_short"))
        self.balance_reset.setText(tr("eq.reset_short"))
        if not self._engine.balance_supported:
            self.balance.setToolTip(tr("eq.balance_unavailable"))
        self._sync()
        self._balance_changed(self.balance.value())

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().hideEvent(event)
