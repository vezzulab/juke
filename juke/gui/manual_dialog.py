"""The manual, inside Juke: an index of chapters on the left and the page on the right, like a book."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter, QTextBrowser, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import manual
from ..i18n import tr, translator

CHAPTER_ROLE = Qt.UserRole
SECTION_ROLE = Qt.UserRole + 1


class ManualDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("manual.title"))
        self.resize(1040, 720)
        self.setMinimumSize(QSize(720, 480))
        self._chapters: list[manual.Chapter] = []
        self._current = -1

        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.index = QTreeWidget()
        self.index.setHeaderHidden(True)
        self.index.setIndentation(14)
        self.index.setUniformRowHeights(True)
        self.index.setMinimumWidth(230)
        self.index.itemClicked.connect(self._picked)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)
        self.contents = QLabel()
        self.contents.setObjectName("muted")
        left_layout.addWidget(self.contents)
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.index, 1)

        self.page = QTextBrowser()
        self.page.setOpenExternalLinks(True)
        self.page.setSearchPaths([str(manual.MANUAL_DIR)])
        self.page.document().setDocumentMargin(26)
        self.chapter_title = QLabel()
        self.chapter_title.setObjectName("heading")
        self.position = QLabel()
        self.position.setObjectName("muted")
        self.previous = QPushButton()
        self.next = QPushButton()
        self.previous.clicked.connect(lambda: self.show_chapter(self._current - 1))
        self.next.clicked.connect(lambda: self.show_chapter(self._current + 1))
        foot = QHBoxLayout()
        foot.addWidget(self.previous)
        foot.addStretch(1)
        foot.addWidget(self.position)
        foot.addStretch(1)
        foot.addWidget(self.next)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self.chapter_title)
        right_layout.addWidget(self.page, 1)
        right_layout.addLayout(foot)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([270, 770])
        split.setChildrenCollapsible(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.addWidget(split, 1)

        self.search.textChanged.connect(self._filter)
        translator.changed.connect(self.retranslate)
        self.retranslate()

    # -- content ------------------------------------------------------------------------------
    def retranslate(self) -> None:
        """(Re)build the index in the language of the app; the manual changes language with it."""
        remembered = self._current
        self.setWindowTitle(tr("manual.title"))
        self.contents.setText(tr("manual.contents"))
        self.search.setPlaceholderText(tr("manual.search"))
        self.previous.setText(tr("manual.previous"))
        self.next.setText(tr("manual.next"))
        self._chapters = manual.load(translator.code, "linux")
        self.index.clear()
        for number, chapter in enumerate(self._chapters):
            top = QTreeWidgetItem(self.index, [f"{number + 1}.  {chapter.title}"])
            top.setData(0, CHAPTER_ROLE, number)
            for section in chapter.sections:
                child = QTreeWidgetItem(top, [section])
                child.setData(0, CHAPTER_ROLE, number)
                child.setData(0, SECTION_ROLE, section)
        self.show_chapter(max(0, remembered))

    def show_chapter(self, number: int, section: str = "") -> None:
        if not 0 <= number < len(self._chapters):
            return
        self._current = number
        chapter = self._chapters[number]
        self.chapter_title.setText(f"{number + 1}.  {chapter.title}")
        self.page.setMarkdown(chapter.body)
        self.position.setText(tr("manual.position", n=number + 1, total=len(self._chapters)))
        self.previous.setEnabled(number > 0)
        self.next.setEnabled(number < len(self._chapters) - 1)
        top = self.index.topLevelItem(number)
        if top is not None:
            self.index.blockSignals(True)
            self.index.setCurrentItem(top)
            self.index.blockSignals(False)
        if section:
            self._scroll_to(section)
        else:
            self.page.verticalScrollBar().setValue(0)

    def _scroll_to(self, heading: str) -> None:
        cursor = self.page.document().find(heading, 0, QTextDocument.FindCaseSensitively)
        if not cursor.isNull():
            self.page.setTextCursor(cursor)
            self.page.ensureCursorVisible()
            at = self.page.cursorRect().top() + self.page.verticalScrollBar().value() - 12
            self.page.verticalScrollBar().setValue(max(0, at))     # the heading at the top of the page
            cursor.clearSelection()
            self.page.setTextCursor(cursor)

    def _picked(self, item: QTreeWidgetItem) -> None:
        number = item.data(0, CHAPTER_ROLE)
        section = item.data(0, SECTION_ROLE) or ""
        if number == self._current and section:
            self._scroll_to(section)
        elif number is not None:
            self.show_chapter(int(number), section)

    def _filter(self, text: str) -> None:
        """Typing narrows the index to the chapters and sections that mention it, and opens the first one."""
        needle = text.strip().casefold()
        first = -1
        for number in range(self.index.topLevelItemCount()):
            top = self.index.topLevelItem(number)
            chapter = self._chapters[number]
            in_chapter = not needle or needle in chapter.body.casefold() or needle in chapter.title.casefold()
            top.setHidden(not in_chapter)
            top.setExpanded(bool(needle) and in_chapter)
            if in_chapter and first < 0 and needle:
                first = number
        if first >= 0:
            self.show_chapter(first)
            cursor = self.page.document().find(text.strip(), 0)
            if not cursor.isNull():
                self.page.setTextCursor(cursor)
                self.page.ensureCursorVisible()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_F and event.modifiers() & Qt.ControlModifier:
            self.search.setFocus()
            self.search.selectAll()
            return
        super().keyPressEvent(event)
