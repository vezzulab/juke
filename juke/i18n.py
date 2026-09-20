"""Runtime translation (English / Spanish) with live language switching."""

from __future__ import annotations

import os

from PySide6.QtCore import QLocale, QObject, Signal

from .locales import en, es

LANGUAGES = {"en": ("English", en.STRINGS), "es": ("Español", es.STRINGS)}


def detect_language() -> str:
    """System language: Spanish if the locale says so, English otherwise."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "es" if value.lower().startswith("es") else "en"
    return "es" if QLocale.system().name().lower().startswith("es") else "en"


class Translator(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.code = "en"

    def set_language(self, setting: str) -> None:
        """``setting`` is "auto", "en" or "es"."""
        code = detect_language() if setting not in LANGUAGES else setting
        if code != self.code:
            self.code = code
            self.changed.emit()

    def tr(self, key: str, **values) -> str:
        text = LANGUAGES[self.code][1].get(key) or en.STRINGS.get(key) or key
        return text.format(**values) if values else text

    def count(self, key: str, n: int, **values) -> str:
        """Pluralised text: ``key_one`` for 1, ``key_other`` otherwise ({n} is localised)."""
        suffix = "_one" if n == 1 else "_other"
        return self.tr(key + suffix, n=QLocale(self.code).toString(n), **values)


translator = Translator()
tr = translator.tr
trn = translator.count
