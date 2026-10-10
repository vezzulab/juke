"""The "what is new" window shown once, the first time a version that has news is run."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout

from ..assets import ICON_SVG
from ..i18n import tr
from . import icons, styles

# version -> the news worth a window: (icon, tone, title key, text key) for the cards, then the short lines
NEWS: dict[str, dict] = {
    "1.0.3": {
        "cards": [("queue", "accent", "news.103.queue.title", "news.103.queue.text"),
                  ("heart", "rose", "news.103.fav.title", "news.103.fav.text")],
        "lines": ["news.103.line1", "news.103.line2"],
    },
}


def has_news(version: str) -> bool:
    return version in NEWS


class WhatsNewDialog(QDialog):
    def __init__(self, version: str, parent=None) -> None:
        super().__init__(parent)
        news = NEWS[version]
        self.setWindowTitle(tr("news.window", version=version))
        self.setFixedWidth(540)

        picture = QLabel()
        picture.setPixmap(icons.render_svg(ICON_SVG.read_bytes(), 52))
        headline = QLabel(tr("news.headline", version=version))
        headline.setObjectName("heading")
        sub = QLabel(tr("news.sub"))
        sub.setObjectName("muted")
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(headline)
        titles.addWidget(sub)
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(picture, 0, Qt.AlignTop)
        head.addLayout(titles, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(12)
        layout.addLayout(head)
        layout.addSpacing(4)
        for glyph, tone, title_key, text_key in news["cards"]:
            layout.addWidget(self._card(glyph, tone, tr(title_key), tr(text_key)))
        for key in news["lines"]:
            line = QLabel("•  " + tr(key))
            line.setWordWrap(True)
            line.setObjectName("muted")
            layout.addWidget(line)

        ok = QPushButton(tr("news.ok"))
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(ok)
        layout.addSpacing(6)
        layout.addLayout(buttons)
        layout.activate()
        self.setFixedHeight(layout.totalHeightForWidth(540) if layout.hasHeightForWidth() else self.sizeHint().height())

    @staticmethod
    def _card(glyph: str, tone: str, title: str, text: str) -> QFrame:
        color = styles.RED if tone == "rose" else styles.ACCENT
        card = QFrame()
        card.setObjectName("newsCard")
        card.setStyleSheet(f"QFrame#newsCard {{ background: {styles.rgba(color, 0.11)}; border: 1px solid "
                           f"{styles.rgba(color, 0.55)}; border-radius: 14px; }} QFrame#newsCard QLabel {{ background: transparent; }}")
        icon = QLabel()
        icon.setPixmap(icons.icon(glyph, color, size=26).pixmap(26, 26))
        icon.setFixedSize(32, 32)
        icon.setAlignment(Qt.AlignCenter)
        name = QLabel(title)
        name.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {color};")
        body = QLabel(text)
        body.setWordWrap(True)
        body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        words = QVBoxLayout()
        words.setSpacing(3)
        words.addWidget(name)
        words.addWidget(body)
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(14)
        row.addWidget(icon, 0, Qt.AlignTop)
        row.addLayout(words, 1)
        return card
