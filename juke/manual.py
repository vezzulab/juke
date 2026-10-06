"""The manual: one book in Markdown per language, shared by Juke for Linux and Juke for Android.

The text lives in ``assets/manual/manual-en.md`` and ``manual-es.md``. Parts that only apply to one system sit between
``<!--linux-->`` and ``<!--/linux-->`` (or ``android``); each app keeps its own and drops the other's, so the same
files serve both and also read as a complete book on GitHub. Chapters start with ``# N. Title`` and sections with
``## Title``. The numbers in the files are for readers of the raw text: the apps number the chapters they show.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MANUAL_DIR = Path(__file__).resolve().parent / "assets" / "manual"
LANGUAGES = ("en", "es")
_TAG = re.compile(r"<!--(linux|android)-->(.*?)<!--/\1-->", re.DOTALL)
_NUMBER = re.compile(r"^\s*\d+\.\s*")


@dataclass(slots=True)
class Chapter:
    title: str
    body: str                                   # Markdown, without the chapter's own heading
    sections: list[str] = field(default_factory=list)


def for_platform(text: str, platform: str) -> str:
    """Keep what belongs to ``platform`` (and to everyone), drop what belongs to the other system."""
    kept = _TAG.sub(lambda m: m.group(2) if m.group(1) == platform else "", text)
    kept = re.sub(r"\n\s*---\s*(?=\n)", "\n", kept)                  # rules between chapters: the app draws its own
    return re.sub(r"\n{3,}", "\n\n", kept).strip() + "\n"


def split_chapters(text: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    lines: list[str] = []
    in_code = False

    def close() -> None:
        if chapters:
            chapters[-1].body = "\n".join(lines).strip() + "\n"

    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        if not in_code and line.startswith("# "):
            close()
            chapters.append(Chapter(_NUMBER.sub("", line[2:]).strip(), ""))
            lines = []
            continue
        if chapters:
            lines.append(line)
            if not in_code and line.startswith("## "):
                chapters[-1].sections.append(line[3:].strip())
    close()
    return [c for c in chapters if c.body.strip()]


def load(language: str, platform: str = "linux") -> list[Chapter]:
    """The chapters of the manual in ``language`` ("en" or "es") for ``platform`` ("linux" or "android")."""
    code = language if language in LANGUAGES else "en"
    text = (MANUAL_DIR / f"manual-{code}.md").read_text(encoding="utf-8")
    return split_chapters(for_platform(text, platform))
