"""A small log file, so a person can read what Juke has been doing and send it along with a problem report.

Nothing leaves the computer by itself. Whatever is shown or copied goes through ``redact`` first: your home
folder, passwords, login tokens and the address of your own server are hidden.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import re
import sys
import threading
from pathlib import Path
from typing import Iterable

from . import __version__
from .config import DATA_DIR

LOG_PATH = DATA_DIR / "juke.log"
_LIMIT = 512 * 1024                 # the file keeps about this much, plus one older copy
_log = logging.getLogger("juke")

_QUERY_SECRET = re.compile(r"(?i)([?&;](?:p|t|s|u|pass|password|token|salt|apikey|api_key|key|auth)=)[^&\s\"']+")
_URL_LOGIN = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")


def setup() -> None:
    """Start writing ``juke.log`` (rotating) and record crashes that would otherwise only reach a terminal."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=_LIMIT, backupCount=1, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    if any(isinstance(h, logging.handlers.RotatingFileHandler) and getattr(h, "baseFilename", "") == str(LOG_PATH) for h in root.handlers):
        return
    root.addHandler(handler)
    root.setLevel(logging.WARNING)                  # libraries only when something is wrong (they may print addresses)
    _log.setLevel(logging.INFO)
    logging.captureWarnings(True)

    previous = sys.excepthook

    def crashed(kind, error, trace):
        _log.critical("Uncaught exception", exc_info=(kind, error, trace))
        previous(kind, error, trace)

    sys.excepthook = crashed
    inherited = threading.excepthook

    def thread_crashed(args):
        _log.critical("Uncaught exception in thread %s", getattr(args.thread, "name", "?"),
                      exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        inherited(args)

    threading.excepthook = thread_crashed
    _log.info("---- Juke %s starting ----", __version__)
    for line in system_summary().splitlines():
        _log.info(line)


def qt_messages() -> None:
    """Qt's own warnings (missing plugins, drawing problems) into the same file."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR, QtMsgType.QtFatalMsg: logging.CRITICAL}
    qt_log = logging.getLogger("juke.qt")

    def handler(kind, _context, message):
        if kind in levels:
            qt_log.log(levels[kind], "%s", message)
        else:
            print(message, file=sys.stderr)

    qInstallMessageHandler(handler)


def system_summary() -> str:
    """Version and system facts that help someone reproduce a problem."""
    lines = [f"Juke {__version__}" + (" (AppImage)" if os.environ.get("APPIMAGE") else "")]
    lines.append(f"System: {_os_name()} · {platform.machine()}")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "?")
    lines.append(f"Desktop: {desktop} · session {os.environ.get('XDG_SESSION_TYPE', '?')}")
    try:
        import PySide6
        from PySide6.QtCore import qVersion

        lines.append(f"Python {platform.python_version()} · PySide6 {PySide6.__version__} · Qt {qVersion()}")
    except Exception:
        lines.append(f"Python {platform.python_version()}")
    try:
        import vlc

        version = vlc.libvlc_get_version()
        lines.append("libVLC " + (version.decode() if isinstance(version, bytes) else str(version)).split(" ")[0])
    except Exception:
        lines.append("libVLC: not available")
    return "\n".join(lines)


def _os_name() -> str:
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.platform()


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Hide what should never be pasted into a public place."""
    for secret in sorted({s for s in secrets if s and len(s) >= 3}, key=len, reverse=True):
        text = text.replace(secret, "<hidden>")
    text = _URL_LOGIN.sub(r"\1<hidden>@", text)
    text = _QUERY_SECRET.sub(r"\1<hidden>", text)
    home = str(Path.home())
    if len(home) > 1:
        text = text.replace(home, "~")
    return text


def read(secrets: Iterable[str] = (), max_bytes: int = 400_000) -> str:
    """The newest part of the log, redacted (empty when nothing has been written yet)."""
    chunks: list[str] = []
    size = 0
    for path in (Path(str(LOG_PATH) + ".1"), LOG_PATH):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        chunks.append(data.decode("utf-8", "replace"))
        size += len(data)
    text = "".join(chunks)
    if len(text) > max_bytes:
        text = text[-max_bytes:]
        text = text[text.find("\n") + 1:]
    return redact(text, secrets)
