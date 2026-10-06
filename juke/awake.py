"""Keep the computer awake while music is playing.

A laptop that goes to sleep in the middle of a song, or of a party, is a laptop nobody can trust. Desktops decide when
to sleep or blank the screen after a while without keyboard or mouse; a player has to ask them not to while it plays.
There is no single way to ask, so Juke asks in every standard way that is there:

* ``org.freedesktop.PowerManagement.Inhibit``: KDE Plasma (PowerDevil) and the desktops that follow it;
* ``org.freedesktop.ScreenSaver.Inhibit``: the common screen saver protocol (KDE, Cinnamon, MATE, XFCE…);
* systemd-logind ``Inhibit("idle:sleep")``: anything that follows the system's own idle action.

It asks when playback starts and lets go the moment it pauses or stops, so nothing is held while nothing plays and
nothing is polled. The asking is done on a connection of its own to the session bus: all of these protocols end the
request when the connection that made it goes away, so letting go is closing that connection (which also means a Juke
that crashes never leaves the computer unable to sleep). Closing the lid is a different decision, the person's, made
in the desktop's power settings, and is not overridden.
"""

from __future__ import annotations

import itertools
import logging

from PySide6.QtCore import QObject
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

log = logging.getLogger("juke")

APP = "Juke"
REASON = "Playing music"
TIMEOUT_MS = 1500
_connections = itertools.count(1)


def _call(bus: QDBusConnection, service: str, path: str, interface: str, method: str, *args):
    """One D-Bus call to a service that is already running (so nothing gets started for it); None on any failure."""
    if not bus.isConnected() or not bus.interface().isServiceRegistered(service).value():
        return None
    iface = QDBusInterface(service, path, interface, bus)
    iface.setTimeout(TIMEOUT_MS)
    reply = iface.call(method, *args)
    if reply.type() != QDBusMessage.ReplyMessage:
        return None
    arguments = reply.arguments()
    return arguments[0] if arguments else True


class StayAwake(QObject):
    """``set(True)`` while something plays, ``set(False)`` when it stops."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.active = False
        self.enabled = True                                # False: never ask (tests, or the person turned it off)
        self.methods: list[str] = []                       # which ways worked, for the log and the tests
        self._session_name = ""                            # the connection the requests were made on
        self._lock = None                                  # the logind lock: a file descriptor, closed to let go

    def set(self, on: bool) -> None:
        if not self.enabled:
            on = False
        if on and not self.active:
            self._acquire()
        elif not on and self.active:
            self._let_go()

    # -- asking ------------------------------------------------------------------------------------------
    def _acquire(self) -> None:
        self.active = True
        self.methods = []
        self._session_name = f"juke-awake-{next(_connections)}"
        session = QDBusConnection.connectToBus(QDBusConnection.SessionBus, self._session_name)

        if _call(session, "org.freedesktop.PowerManagement.Inhibit", "/org/freedesktop/PowerManagement/Inhibit",
                 "org.freedesktop.PowerManagement.Inhibit", "Inhibit", APP, REASON) is not None:
            self.methods.append("PowerManagement")

        for path in ("/org/freedesktop/ScreenSaver", "/ScreenSaver"):          # (KDE also answers on the short path)
            if _call(session, "org.freedesktop.ScreenSaver", path, "org.freedesktop.ScreenSaver", "Inhibit", APP, REASON) is not None:
                self.methods.append("ScreenSaver")
                break

        lock = _call(QDBusConnection.systemBus(), "org.freedesktop.login1", "/org/freedesktop/login1",
                     "org.freedesktop.login1.Manager", "Inhibit", "idle:sleep", APP, REASON, "block")
        if lock is not None and lock is not True:
            self._lock = lock
            self.methods.append("logind")

        if self.methods:
            log.info("Keeping the computer awake while playing (%s)", ", ".join(self.methods))
        else:
            log.warning("Could not ask the desktop to stay awake while playing: the computer may go to sleep")

    # -- letting go -------------------------------------------------------------------------------------
    def _let_go(self) -> None:
        self.active = False
        self._lock = None                                  # closes the logind descriptor
        if self._session_name:
            QDBusConnection.disconnectFromBus(self._session_name)      # the desktop drops what this connection asked for
            self._session_name = ""
        self.methods = []
