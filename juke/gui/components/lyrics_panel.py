"""The lyrics column on the right: shown by itself when the playing song has lyrics, following the song line by line
when the lyrics are synced (.lrc)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QStackedWidget, QTextEdit, QToolButton,
                               QVBoxLayout, QWidget)

from ... import lyrics as lyrics_lib
from ...i18n import tr
from .. import icons, styles


class LyricsPanel(QWidget):
    edit_requested = Signal()
    find_requested = Signal()
    closed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("lyricsPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._timeline: list[tuple[int, str]] = []
        self._current = -1

        self.heading = QLabel()
        self.heading.setObjectName("heading")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("muted")
        self.subtitle.setWordWrap(False)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(self.heading)
        titles.addWidget(self.subtitle)

        def tool(icon: str, slot) -> QToolButton:
            button = QToolButton()
            button.setObjectName("menuButton")
            button.setIcon(icons.icon(icon, styles.TEXT, size=18))
            button.setFixedSize(32, 32)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(slot)
            return button

        self.find_button = tool("search", self.find_requested.emit)
        self.edit_button = tool("edit", self.edit_requested.emit)
        self.close_button = tool("close", self.closed.emit)
        head = QHBoxLayout()
        head.setContentsMargins(16, 14, 10, 6)
        head.setSpacing(2)
        head.addLayout(titles, 1)
        for button in (self.find_button, self.edit_button, self.close_button):
            head.addWidget(button)

        self.text = QPlainTextEdit()
        self.text.setObjectName("lyricsText")
        self.text.setReadOnly(True)
        self.text.setFrameShape(QPlainTextEdit.NoFrame)
        self.text.document().setDefaultTextOption(QTextOption(Qt.AlignHCenter))
        self.text.setCursorWidth(0)
        self.text.viewport().setCursor(Qt.ArrowCursor)

        self.empty_title = QLabel()
        self.empty_title.setObjectName("heading")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_title.setWordWrap(True)
        self.empty_hint = QLabel()
        self.empty_hint.setObjectName("muted")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.add_button = QPushButton()
        self.add_button.setObjectName("primary")
        self.add_button.clicked.connect(self.edit_requested.emit)
        self.search_button = QPushButton()
        self.search_button.clicked.connect(self.find_requested.emit)
        empty = QWidget()
        column = QVBoxLayout(empty)
        column.setContentsMargins(24, 0, 24, 0)
        column.setSpacing(10)
        column.addStretch(1)
        for widget in (self.empty_title, self.empty_hint):
            column.addWidget(widget)
        column.addSpacing(6)
        column.addWidget(self.add_button)
        column.addWidget(self.search_button)
        column.addStretch(2)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.text)
        self.pages.addWidget(empty)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(head)
        layout.addWidget(self.pages, 1)
        self.setMinimumWidth(260)
        self.retranslate()
        styles.signals.changed.connect(lambda _n: self.apply_theme())

    def retranslate(self) -> None:
        self.heading.setText(tr("lyrics.title"))
        self.find_button.setToolTip(tr("lyrics.find"))
        self.edit_button.setToolTip(tr("lyrics.edit"))
        self.close_button.setToolTip(tr("lyrics.hide"))
        self.empty_title.setText(tr("lyrics.none"))
        self.empty_hint.setText(tr("lyrics.none_hint"))
        self.add_button.setText(tr("lyrics.add"))
        self.search_button.setText(tr("lyrics.find"))

    def apply_theme(self) -> None:
        for button, icon in ((self.find_button, "search"), (self.edit_button, "edit"), (self.close_button, "close")):
            button.setIcon(icons.icon(icon, styles.TEXT, size=18))
        self._paint()

    # -- content -----------------------------------------------------------------------------------------
    def set_song(self, title: str, artist: str) -> None:
        self.subtitle.setText(f"{title} — {artist}" if artist else title)

    def set_lyrics(self, text: str) -> None:
        """Show ``text`` (plain or .lrc). Empty text shows the invitation to add or search for lyrics."""
        self._current = -1
        self._timeline = lyrics_lib.parse_lrc(text) if lyrics_lib.is_synced(text) else []
        if not text.strip():
            self.text.clear()
            self.pages.setCurrentIndex(1)
            return
        body = "\n".join(words for _ms, words in self._timeline) if self._timeline else lyrics_lib.plain_text(text)
        self.text.setPlainText(body)
        self.pages.setCurrentIndex(0)
        self.text.verticalScrollBar().setValue(0)
        self._paint()

    @property
    def has_lyrics(self) -> bool:
        return self.pages.currentIndex() == 0

    def set_position(self, position_ms: int) -> None:
        if not self._timeline:
            return
        index = lyrics_lib.line_at(self._timeline, position_ms)
        if index != self._current:
            self._current = index
            self._paint()

    def _paint(self) -> None:
        """Light up the line being sung and keep it in the middle of the column."""
        if not self._timeline or self._current < 0:
            self.text.setExtraSelections([])
            return
        block = self.text.document().findBlockByNumber(self._current)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.LineUnderCursor)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(styles.ACCENT))
        fmt.setFontWeight(700)
        fmt.setBackground(styles.qcolor(styles.ACCENT, 34))
        selection = QTextEdit.ExtraSelection()
        selection.cursor, selection.format = cursor, fmt
        self.text.setExtraSelections([selection])
        focus = QTextCursor(block)
        self.text.setTextCursor(focus)
        self.text.centerCursor()
