"""Floating equalizer window: 10-band graphic EQ, presets, preamp, speed and balance."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QSlider, QStyle, QStyleOptionSlider, QVBoxLayout, QWidget)

from ...audio.engine import AudioEngine
from ...audio.equalizer import BAND_GROUPS, ADVANCED_DEFAULT, ADVANCED_LEVELS, BAND_LABELS, BANDS_HZ, MAX_DB, MIN_DB, SETUPS, Equalizer
from ...i18n import tr
from .. import styles
from ..dialogs import ask_text, notice
from .widgets import JumpSlider

SCALE = 10  # slider units per dB


class EqSlider(QSlider):
    """A vertical bar with its own ruler: a line every 5 dB (0 dB stronger), drawn behind the groove, so you can read
    where the bar stands without looking at the number."""

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Vertical, parent)
        self.setMinimumWidth(52)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self).height() or 14
        span = max(1, self.height() - handle)
        middle = self.width() / 2
        for db in range(int(MIN_DB), int(MAX_DB) + 1, 5):
            y = handle / 2 + QStyle.sliderPositionFromValue(self.minimum(), self.maximum(), db * SCALE, span, True)
            half = 22 if db == 0 else (14 if db % 10 == 0 else 8)
            painter.setPen(QPen(QColor(styles.TEXT if db == 0 else styles.MUTED), 1.6 if db == 0 else 1))
            painter.setOpacity(0.9 if db == 0 else 0.55)
            painter.drawLine(QPointF(middle - half, y), QPointF(middle + half, y))
        painter.end()
        super().paintEvent(event)


class VerticalLabel(QWidget):
    """Text turned to read from the bottom up, set beside its bar and centred on the bar's height."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._text = text

    def setText(self, text: str) -> None:  # noqa: N802
        self._text = text
        self.updateGeometry()
        self.update()

    def sizeHint(self):  # noqa: N802
        metrics = self.fontMetrics()
        return QSize(metrics.height() + 4, 40)

    def minimumSizeHint(self):  # noqa: N802
        return QSize(self.fontMetrics().height() + 4, 40)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(QColor(styles.SUBTEXT))
        painter.translate(0, self.height())
        painter.rotate(-90)
        painter.drawText(QRectF(0, 0, self.height(), self.width()), Qt.AlignCenter, self._text)


class CurveWidget(QWidget):
    """Smooth response curve drawn through the ten band gains."""

    def __init__(self, equalizer: Equalizer, parent=None) -> None:
        super().__init__(parent)
        self._eq = equalizer
        self.detailed = False                              # the advanced view: dB grid and a frequency under every point
        self.setMinimumHeight(80)

    def set_detailed(self, detailed: bool) -> None:
        self.detailed = detailed
        self.setMinimumHeight(130 if detailed else 80)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad = 14.0
        painter.setPen(QPen(QColor(styles.BORDER), 1))
        painter.drawLine(QPointF(pad, h / 2), QPointF(w - pad, h / 2))
        gains = self._eq.effective_gains()
        limit = 12.0
        if self.detailed:
            painter.setPen(QPen(QColor(styles.BORDER), 1, Qt.DotLine))
            for db in (-12, -6, 6, 12):
                y = h / 2 - (db / limit) * (h / 2 - 10)
                painter.drawLine(QPointF(pad + 26, y), QPointF(w - pad, y))
            painter.setPen(QColor(styles.MUTED))
            for db in (-12, -6, 0, 6, 12):
                y = h / 2 - (db / limit) * (h / 2 - 10)
                painter.drawText(QPointF(2, y + 4), f"{db:+d}" if db else "0")
        xs = [pad + (w - 2 * pad) * i / 9 for i in range(10)]
        total = [max(-limit, min(limit, g + self._eq.effective_preamp())) for g in gains]
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
        self.btn_advanced = QPushButton()                  # opens the bigger equalizer with the echo / reverb controls
        self.btn_advanced.setCheckable(True)
        self.curve = CurveWidget(equalizer)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self.enabled)
        top.addStretch(1)
        top.addWidget(self.presets)
        top.addWidget(self.btn_save)
        top.addWidget(self.btn_delete)
        top.addWidget(self.btn_reset)
        top.addWidget(self.btn_advanced)

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
        self.song_preset = QPushButton()                   # keeps the song's curve in the preset it came from as well
        self.song_preset.clicked.connect(self._song_to_preset)
        note = QHBoxLayout()
        note.addWidget(self.song_note, 1)
        note.addWidget(self.song_preset)
        note.addWidget(self.song_back)
        self.song_bar = QWidget()
        self.song_bar.setLayout(note)
        self.song_bar.hide()
        self.band_sliders: list[QSlider] = []
        self.band_values: list[QLabel] = []
        self.band_names: list[VerticalLabel] = []         # "Deep bass", "Voice"...: what the bar changes, in plain words
        self.band_freqs: list[QLabel] = []
        self.group_labels: dict[str, QLabel] = {}

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)
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
            nick = VerticalLabel()
            self.band_sliders.append(slider)
            self.band_values.append(value)
            self.band_freqs.append(freq)
            self.band_names.append(nick)
            self._add_column(grid, i + 2, value, slider, freq, side=nick)
            group = BAND_GROUPS[i]
            first_of.setdefault(group, i + 2)
            count_of[group] = count_of.get(group, 0) + 1
            slider.valueChanged.connect(lambda v, idx=i: self._eq.set_band(idx, v / SCALE - self._eq.setup_offsets()[idx]))
        for group, column in first_of.items():          # BASS / MIDDLE / TREBLE over the bars they cover
            caption = QLabel()
            caption.setAlignment(Qt.AlignCenter)
            caption.setObjectName("eqGroup")
            self.group_labels[group] = caption
            grid.addWidget(caption, 4, column, 1, count_of[group])
        self.preamp_slider.valueChanged.connect(lambda v: self._eq.set_preamp(v / SCALE - self._eq.setup_preamp_offset()))

        self.extras = QGroupBox()
        extras = QGridLayout(self.extras)
        extras.setHorizontalSpacing(10)
        extras.setVerticalSpacing(6)
        self.setup_label = QLabel()                         # where and how you listen: tabs that add to the curve
        self.setup_buttons: dict[str | None, QPushButton] = {}
        self.setup_group = QButtonGroup(self)
        self.setup_group.setExclusive(True)
        setup_row = QHBoxLayout()
        setup_row.setSpacing(4)
        for name in (None, *SETUPS):
            button = QPushButton()
            button.setObjectName("deckBtn")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self.setup_group.addButton(button)
            self.setup_buttons[name] = button
            setup_row.addWidget(button)
            button.clicked.connect(lambda _=False, n=name: self._eq.set_setup(n))
        setup_row.addStretch(1)
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
        extras.addWidget(self.setup_label, 0, 0)
        extras.addLayout(setup_row, 0, 1, 1, 7)
        for n, (label, slider, value, reset) in enumerate((
                (self.speed_label, self.speed, self.speed_value, self.speed_reset),
                (self.balance_label, self.balance, self.balance_value, self.balance_reset))):
            extras.addWidget(label, 1, 4 * n)
            extras.addWidget(slider, 1, 4 * n + 1)
            extras.addWidget(value, 1, 4 * n + 2)
            extras.addWidget(reset, 1, 4 * n + 3)
        extras.setColumnStretch(1, 1)
        extras.setColumnStretch(5, 1)
        self.balance.setEnabled(engine.balance_supported)
        self.balance_reset.setEnabled(engine.balance_supported)

        self.adv_box = QGroupBox()
        adv = QGridLayout(self.adv_box)
        adv.setHorizontalSpacing(12)
        adv.setVerticalSpacing(6)
        adv.setContentsMargins(10, 4, 10, 8)
        # A deck: one card per control, each with its own row of buttons (nothing to drag).
        self.adv_cards: dict[str, tuple[QLabel, dict[int, QPushButton]]] = {}
        for n, key in enumerate(ADVANCED_DEFAULT):
            card = QFrame()
            card.setObjectName("eqCard")
            box = QVBoxLayout(card)
            box.setContentsMargins(8, 7, 8, 8)
            box.setSpacing(5)
            name = QLabel()
            name.setObjectName("deckTitle")
            name.setWordWrap(True)
            box.addWidget(name)
            row, buttons = QHBoxLayout(), {}
            row.setSpacing(3)
            for value in ADVANCED_LEVELS[key]:
                button = QPushButton()
                button.setObjectName("deckBtn")
                button.setCheckable(True)
                button.setCursor(Qt.PointingHandCursor)
                buttons[value] = button
                row.addWidget(button)
                button.clicked.connect(lambda _=False, k=key, v=value: self._eq.set_advanced(k, v))
            box.addLayout(row)
            adv.addWidget(card, 0, n)
            self.adv_cards[key] = (name, buttons)
        self.adv_reset = QPushButton()
        self.adv_reset.clicked.connect(self._eq.reset_advanced)
        adv.addWidget(self.adv_reset, 0, len(ADVANCED_DEFAULT), Qt.AlignBottom)
        for column in range(len(ADVANCED_DEFAULT)):
            adv.setColumnStretch(column, 1)
        self.adv_box.hide()

        inner = QWidget()                                   # everything scrolls, so a short screen never squeezes the bars
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(18, 12, 18, 12)
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)
        scroller.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroller)
        self._inner = inner
        layout.setSpacing(8)
        layout.addLayout(top)
        layout.addWidget(self.song_bar)
        layout.addWidget(self.hint)
        layout.addWidget(self.curve)
        layout.addLayout(grid, 1)
        layout.addWidget(self.adv_box)
        layout.addWidget(self.extras)

        self.enabled.toggled.connect(self._eq.set_enabled)
        self.presets.activated.connect(self._preset_chosen)
        self.btn_save.clicked.connect(self._save_preset)
        self.btn_delete.clicked.connect(self._delete_preset)
        self.btn_reset.clicked.connect(self._eq.reset)
        self.btn_advanced.toggled.connect(self._set_advanced_view)
        self.speed.valueChanged.connect(self._speed_changed)
        self.speed_reset.clicked.connect(lambda: self.speed.setValue(100))
        self.balance.valueChanged.connect(self._balance_changed)
        self.balance_reset.clicked.connect(lambda: self.balance.setValue(0))
        self._eq.changed.connect(self._sync)

        self.retranslate()
        self._sync()
        self._speed_changed(self.speed.value())
        self._balance_changed(self.balance.value())
        self._fit(False)

    # -- construction helpers ---------------------------------------------------------------
    @staticmethod
    def _vertical_slider() -> QSlider:
        slider = EqSlider()
        slider.setRange(int(MIN_DB * SCALE), int(MAX_DB * SCALE))
        slider.setPageStep(5 * SCALE)
        slider.setSingleStep(SCALE // 2)
        slider.setMinimumHeight(120)
        slider.setCursor(Qt.PointingHandCursor)
        return slider

    @staticmethod
    def _value_label() -> QLabel:
        label = QLabel("0.0")
        label.setAlignment(Qt.AlignCenter)
        label.setObjectName("eqValue")
        label.setTextFormat(Qt.RichText)
        label.setMinimumHeight(36)                         # room for the line that says how much a setup moved it
        return label

    @staticmethod
    def _with_delta(value: float, delta: float) -> str:
        text = f"{value:+.1f}"
        if abs(delta) < 0.05:
            return text + "<br>&nbsp;"
        up = delta > 0
        return f"{text}<br><span style='color:{'#3fb950' if up else '#f85149'}'>{'▲' if up else '▼'} {abs(delta):g}</span>"

    @staticmethod
    def _add_column(grid: QGridLayout, column: int, value: QLabel, slider: QSlider, name: QLabel,
                    side: QWidget | None = None) -> None:
        name.setAlignment(Qt.AlignCenter)
        grid.addWidget(value, 0, column, Qt.AlignHCenter)
        if side is None:
            grid.addWidget(slider, 1, column, Qt.AlignHCenter)
        else:                                                # the bar with its name written up its side
            pair = QWidget()
            row = QHBoxLayout(pair)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            row.addWidget(slider)
            row.addWidget(side)
            grid.addWidget(pair, 1, column, Qt.AlignHCenter)
        grid.addWidget(name, 2, column, Qt.AlignHCenter)
        grid.setColumnStretch(column, 1)

    @staticmethod
    def _deck_style() -> str:
        """The advanced controls as a rack module: dark cards, small-caps titles, buttons that light up like LEDs."""
        return (f"QFrame#eqCard {{ background: {styles.BASE}; border: 1px solid {styles.BORDER}; border-radius: 8px; }}"
                f"QLabel#deckTitle {{ color: {styles.SUBTEXT}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}"
                f"QPushButton#deckBtn {{ background: {styles.OVERLAY}; color: {styles.MUTED}; border: 1px solid {styles.BORDER};"
                f" border-radius: 3px; min-height: 24px; padding: 0 1px; font-size: 11px; font-weight: 600; }}"
                f"QPushButton#deckBtn:hover {{ border-color: {styles.ACCENT}; color: {styles.TEXT}; }}"
                f"QPushButton#deckBtn:checked {{ color: {styles.ON_ACCENT}; border: 1px solid {styles.ACCENT};"
                f" background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {styles.ACCENT}, stop:1 {styles.ACCENT2}); }}")

    def _set_advanced_view(self, on: bool) -> None:
        """The bigger equalizer: a graph with its dB grid, the echo / reverb deck, taller bars."""
        self.curve.set_detailed(on)
        self.adv_box.setVisible(on)
        self.hint.setVisible(not on)                         # the line above the graph: the advanced view needs the room
        self.btn_advanced.setText(tr("eq.advanced_close") if on else tr("eq.advanced"))
        self.setMinimumWidth(1200 if on else 860)
        self._fit(on)

    def _fit(self, advanced: bool) -> None:
        """Size the window to its content: the basic one as small as it can be, the advanced one as tall as the screen
        lets it be (the bars take the spare height), so neither needs to scroll."""
        screen = QGuiApplication.primaryScreen()
        room = int(screen.availableGeometry().height() * 0.94) if screen else 900
        need = self._inner.minimumSizeHint().height() + 4
        height = min(room, max(need, 880)) if advanced else min(room, need + 40)
        needed_width = self._inner.minimumSizeHint().width() + 4
        self.resize(max(self.width() if advanced else 0, self.minimumWidth(), needed_width), height)

    # -- state ---------------------------------------------------------------------------------------
    def _sync(self) -> None:
        """Mirror the Equalizer object into every widget without feeding changes back."""
        eq = self._eq
        for widget in (self.enabled, self.presets, self.preamp_slider, *self.band_sliders):
            widget.blockSignals(True)
        self.enabled.setChecked(eq.enabled)
        # With a listening setup the bars show what is really played: yours plus what the setup moved, and each
        # bar it moved says by how much (green up, red down).
        offsets = eq.setup_offsets()
        shown = eq.effective_gains()
        self.preamp_slider.setValue(round(eq.effective_preamp() * SCALE))
        self.preamp_value.setText(self._with_delta(eq.effective_preamp(), eq.effective_preamp() - eq.preamp))
        for slider, label, gain, delta in zip(self.band_sliders, self.band_values, shown, offsets):
            slider.setValue(round(gain * SCALE))
            label.setText(self._with_delta(gain, delta))
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
            self.song_note.setText(tr("eq.song_note", name=eq.origin or eq.preset or tr("eq.custom")))
            mine = eq.origin in eq.custom
            self.song_preset.setText(tr("eq.song_update", name=eq.origin) if mine else tr("eq.song_save"))
        controls_on = eq.enabled
        for slider in (self.preamp_slider, *self.band_sliders):
            slider.setEnabled(controls_on)
        self.btn_delete.setEnabled(eq.preset in eq.custom)
        self.setup_buttons[eq.setup].setChecked(True)
        for key, (_, buttons) in self.adv_cards.items():       # one lit button per card: the level that is on
            nearest = min(buttons, key=lambda v: abs(v - eq.advanced[key]))
            for value, button in buttons.items():
                button.setChecked(value == nearest)
        self.curve.update()

    def _song_to_preset(self) -> None:
        if self._eq.origin in self._eq.custom:
            self._eq.update_preset()
        else:
            self._save_preset()                              # a built-in preset cannot change: keep it as a preset of your own

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
        self.btn_advanced.setText(tr("eq.advanced"))
        self.btn_advanced.setStyleSheet(                    # amber, so the Basic / Advanced switch stands out from the rest
            "QPushButton { background: #f5a524; color: #1e1e2e; border: 1px solid #f5a524; font-weight: 700; }"
            "QPushButton:hover { background: #ffb938; border-color: #ffb938; }"
            "QPushButton:checked { background: #e8890c; border-color: #e8890c; }")
        self.adv_box.setTitle(tr("eq.adv.title"))
        self.adv_box.setStyleSheet(self._deck_style())
        self.extras.setStyleSheet(self._deck_style())
        self.adv_box.setToolTip(tr("eq.adv.note"))
        for key, (name, buttons) in self.adv_cards.items():
            name.setText(tr(f"eq.adv.{key}").upper())
            for value, button in buttons.items():
                button.setText(f"{value}%" if key == "room" else tr(f"eq.adv.level.{value}"))
                button.setToolTip(tr(f"eq.adv.{key}.about"))
        self.adv_reset.setText(tr("eq.reset_short"))
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
        self.setup_label.setText(tr("eq.setup"))
        for name, button in self.setup_buttons.items():
            button.setText(tr("eq.setup.none") if name is None else tr("eq.setup." + name))
            button.setToolTip(tr("eq.setup.about"))
        self.speed_label.setText(tr("eq.speed"))
        self.balance_label.setText(tr("eq.balance"))
        self.speed_reset.setText(tr("eq.reset_short"))
        self.balance_reset.setText(tr("eq.reset_short"))
        if not self._engine.balance_supported:
            self.balance.setToolTip(tr("eq.balance_unavailable"))
        self._sync()
        self._balance_changed(self.balance.value())

    def showEvent(self, event) -> None:  # noqa: N802
        if not getattr(self, "_fitted", False):             # the first time the fonts and styles are real, so the size is too
            self._fitted = True
            self._fit(self.btn_advanced.isChecked())
        super().showEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().hideEvent(event)
