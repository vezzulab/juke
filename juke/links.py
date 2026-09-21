"""Opening links (a web page, a folder) from inside the AppImage.

The AppImage starts Juke with its own libraries and Python first in ``LD_LIBRARY_PATH``, ``PYTHONHOME``, ``PATH``
and friends. A browser started by ``xdg-open`` inherits that and quietly fails to start, so the button seems to
do nothing. Links are opened with the environment the desktop gave the AppImage instead.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QUrl, Slot
from PySide6.QtGui import QDesktopServices

from .i18n import tr

log = logging.getLogger(__name__)

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


def _via_portal(target: str) -> bool:
    """Ask the desktop itself to open the address (the freedesktop portal, over D-Bus). Nothing is launched from here, so
    what the AppImage put in the environment cannot get in the way."""
    if not target.startswith(("http:", "https:", "mailto:")):
        return False
    try:
        from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        message = QDBusMessage.createMethodCall("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                                                "org.freedesktop.portal.OpenURI", "OpenURI")
        message.setArguments(["", target, {}])
        reply = bus.call(message, QDBus.CallMode.Block, 4000)
        if reply.type() == QDBusMessage.MessageType.ReplyMessage:
            return True
        log.info("The desktop portal did not open %s: %s", target, reply.errorMessage())
    except Exception as exc:                                   # no D-Bus, no portal: the next way is tried
        log.info("The desktop portal is not available: %s", exc)
    return False


def _started(result) -> bool:
    """``QProcess.startDetached()`` gives (started, pid) in some PySide6 builds and just ``started`` in others."""
    return bool(result[0] if isinstance(result, tuple) else result)


def _via_program(target: str) -> bool:
    environment = QProcessEnvironment()
    for key, value in desktop_environment().items():
        environment.insert(key, value)
    for program, args in (("xdg-open", [target]), ("gio", ["open", target]), ("kde-open", [target]), ("kde-open5", [target])):
        process = QProcess()
        process.setProcessEnvironment(environment)
        process.setProgram(program)
        process.setArguments(args)
        started = _started(process.startDetached())
        if started:
            log.info("Opened %s with %s", target, program)
            return True
    return False


def open_url(url: QUrl | str) -> bool:
    """Open ``url`` in the default browser or file manager. If nothing on the system can, the address is copied to the
    clipboard and the person is told, so the click is never silent."""
    target = url.toString() if isinstance(url, QUrl) else str(url)
    if _via_portal(target):
        log.info("Opened %s through the desktop portal", target)
        return True
    if _via_program(target):
        return True
    log.warning("Could not open %s: no portal, xdg-open, gio or kde-open answered", target)
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QMessageBox

        QGuiApplication.clipboard().setText(target)
        QMessageBox.information(QGuiApplication.focusWindow() and None, tr("links.title"), tr("links.copied", url=target))
    except Exception:
        pass
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
