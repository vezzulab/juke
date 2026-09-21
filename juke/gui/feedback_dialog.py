"""Send feedback (a problem, an idea, a question) and read Juke's log. Nothing is sent by Juke itself: the report
is opened as a new issue on GitHub, where the person reviews it and presses the button, or it is copied."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, QUrlQuery
from PySide6.QtGui import QDesktopServices, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from .. import REPO_URL, applog
from ..i18n import tr

_URL_BUDGET = 6500          # what is sent in the address; longer than this browsers and GitHub refuse it


def secrets_of(config) -> list[str]:
    """The private bits of the settings, so they can be hidden from anything that is shown or copied."""
    server = config.get("airsonic") or {}
    url = str(server.get("url") or "")
    host = url.split("://", 1)[-1].split("/", 1)[0]
    return [str(server.get("password") or ""), str(server.get("username") or ""), url, host]


class FeedbackDialog(QDialog):
    KINDS = (("problem", "feedback.kind_problem", "Problem"), ("idea", "feedback.kind_idea", "Suggestion"),
             ("question", "feedback.kind_question", "Question"))

    def __init__(self, config, extra_lines: list[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._secrets = secrets_of(config)
        self._extra = extra_lines or []
        self.setWindowTitle(tr("feedback.title"))
        self.setMinimumWidth(640)

        intro = QLabel(tr("feedback.intro"))
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        self.kind = QComboBox()
        for key, label, _en in self.KINDS:
            self.kind.addItem(tr(label), key)
        self.message = QPlainTextEdit()
        self.message.setPlaceholderText(tr("feedback.placeholder"))
        self.message.setMinimumHeight(150)
        self.message.textChanged.connect(self._refresh)
        self.include = QPushButton(tr("feedback.include"))
        self.include.setCheckable(True)
        self.include.setChecked(True)
        self.include.toggled.connect(self._refresh)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.preview.setMinimumHeight(140)
        self.hint = QLabel(tr("feedback.hint"))
        self.hint.setWordWrap(True)
        self.hint.setObjectName("muted")

        self.send = QPushButton(tr("feedback.send"))
        self.send.setObjectName("primary")
        self.send.clicked.connect(self._send)
        copy = QPushButton(tr("feedback.copy"))
        copy.clicked.connect(self._copy)
        cancel = QPushButton(tr("dialog.cancel"))
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(self.send)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(intro)
        layout.addWidget(self.kind)
        layout.addWidget(self.message, 1)
        layout.addWidget(self.include)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.hint)
        layout.addLayout(row)
        self._refresh()

    # -- what will be sent -------------------------------------------------------------------------------
    def details(self, with_log: bool = True) -> str:
        parts = [applog.system_summary(), *self._extra]
        text = "\n".join(parts)
        if with_log:
            log = applog.read(self._secrets, max_bytes=60_000)
            if log:
                text += "\n\n--- log ---\n" + log
        return applog.redact(text, self._secrets)

    def report(self, with_log: bool = True) -> str:
        text = applog.redact(self.message.toPlainText().strip(), self._secrets)      # what was typed too
        if self.include.isChecked():
            text += "\n\n---\n" + self.details(with_log)
        return text

    def _refresh(self) -> None:
        self.include.setText(tr("feedback.include") + ("  ✓" if self.include.isChecked() else ""))
        self.preview.setVisible(self.include.isChecked())
        self.preview.setPlainText(self.details(True) if self.include.isChecked() else "")
        self.send.setEnabled(bool(self.message.toPlainText().strip()))

    def _title(self) -> str:
        typed = applog.redact(self.message.toPlainText().strip(), self._secrets)
        first = typed.splitlines()[0][:70] if typed else ""
        label = next(en for key, _l, en in self.KINDS if key == self.kind.currentData())
        return f"[{label}] {first}".strip()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.report(True))
        self.hint.setText(tr("feedback.copied"))

    def _send(self) -> None:
        """Open a new GitHub issue with the report filled in; the whole thing (log included) is also copied, in
        case the address had to be shortened."""
        QGuiApplication.clipboard().setText(self.report(True))
        body = self.report(False)
        url = self._issue_url(body)
        if len(url.toString()) > _URL_BUDGET:
            body = applog.redact(self.message.toPlainText().strip(), self._secrets)[:2500] + "\n\n" + tr("feedback.paste_rest")
            url = self._issue_url(body)
        QDesktopServices.openUrl(url)
        self.accept()

    def _issue_url(self, body: str) -> QUrl:
        query = QUrlQuery()
        query.addQueryItem("title", self._title())
        query.addQueryItem("body", body)
        url = QUrl(REPO_URL + "/issues/new")
        url.setQuery(query)
        return url


class LogDialog(QDialog):
    """Juke's log, with private details hidden, to read, copy or save."""

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._secrets = secrets_of(config)
        self.setWindowTitle(tr("log.title"))
        self.resize(820, 560)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        note = QLabel(tr("log.note", path=applog.redact(str(applog.LOG_PATH))))
        note.setObjectName("muted")
        note.setWordWrap(True)
        buttons = QDialogButtonBox()
        for label, slot in ((tr("log.refresh"), self.load), (tr("feedback.copy"), self._copy), (tr("log.save"), self._save)):
            button = buttons.addButton(label, QDialogButtonBox.ActionRole)
            button.clicked.connect(slot)
        close = buttons.addButton(tr("dialog.close"), QDialogButtonBox.RejectRole)
        close.clicked.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(note)
        layout.addWidget(self.text, 1)
        layout.addWidget(buttons)
        self.load()

    def load(self) -> None:
        self.text.setPlainText(applog.read(self._secrets) or tr("log.empty"))
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text.toPlainText())

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("log.save"), str(Path.home() / "juke-log.txt"), "Text (*.txt)")
        if path:
            try:
                Path(path).write_text(self.text.toPlainText(), encoding="utf-8")
            except OSError:
                pass
