"""Opening links (a web page, a folder) from inside the AppImage.

The AppImage starts Juke with its own libraries and Python first in ``LD_LIBRARY_PATH``, ``PYTHONHOME``, ``PATH``
and friends. A browser started by ``xdg-open`` inherits that and quietly fails to start, so the button seems to
do nothing. Links are opened with the environment the desktop gave the AppImage instead.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QUrl, Slot
from PySide6.QtGui import QDesktopServices

# set by AppRun for Juke's own use; nothing else should see them
_PRIVATE = ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE", "VLC_PLUGIN_PATH",
            "PYTHON_VLC_LIB_PATH", "MALLOC_ARENA_MAX", "MALLOC_TRIM_THRESHOLD_", "MALLOC_MMAP_THRESHOLD_", "APPDIR")
# lists AppRun added to; the entries that point inside the AppImage come out, the rest stay
_LISTS = ("LD_LIBRARY_PATH", "PATH", "XDG_DATA_DIRS")


def desktop_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """``source`` (default: this process) without what the AppImage added."""
    env = dict(os.environ if source is None else source)
    appdir = env.get("APPDIR", "")
    if appdir:
        for name in _LISTS:
            if name in env:
                kept = [p for p in env[name].split(":") if p and not p.startswith(appdir)]
                if kept:
                    env[name] = ":".join(kept)
                else:
                    del env[name]
        for name in _PRIVATE:
            env.pop(name, None)
    return env


def open_url(url: QUrl | str) -> bool:
    """Open ``url`` in the default browser or file manager. False if nothing on the system could."""
    target = url.toString() if isinstance(url, QUrl) else str(url)
    environment = QProcessEnvironment()
    for key, value in desktop_environment().items():
        environment.insert(key, value)
    for program, args in (("xdg-open", [target]), ("gio", ["open", target]), ("kde-open", [target])):
        process = QProcess()
        process.setProcessEnvironment(environment)
        process.setProgram(program)
        process.setArguments(args)
        started, _pid = process.startDetached()
        if started:
            return True
    return False


class _Opener(QObject):
    @Slot(QUrl)
    def open(self, url: QUrl) -> None:
        open_url(url)


def install_handlers(parent: QObject) -> None:
    """Every link Qt would open itself (buttons, labels, the About box, release notes) goes through ``open_url``."""
    opener = _Opener(parent)
    for scheme in ("http", "https", "file", "mailto"):
        QDesktopServices.setUrlHandler(scheme, opener, "open")
