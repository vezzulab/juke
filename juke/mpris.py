"""Media keys and the desktop's media controls (MPRIS 2).

GNOME, KDE, Cinnamon, XFCE, MATE, Budgie and the rest of the desktops do not hand the play / pause / next / previous
keys to whichever window has focus: they send them over the session bus to the player that says it is one
(``org.mpris.MediaPlayer2.*``). The same service is what the shell's media widget, the lock screen, headset buttons
and ``playerctl`` talk to. Nothing here polls: the bus calls us, and we only speak when something changed.
"""

from __future__ import annotations

import os

from PySide6.QtCore import ClassInfo, Property, QObject, QTimer, Signal, Slot
from PySide6.QtDBus import QDBusAbstractAdaptor, QDBusConnection, QDBusMessage, QDBusObjectPath

from . import APP_ID

PATH = "/org/mpris/MediaPlayer2"
ROOT_IFACE = "org.mpris.MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
LOOP = {"off": "None", "all": "Playlist", "one": "Track"}
LOOP_BACK = {v: k for k, v in LOOP.items()}
STATUS = {"playing": "Playing", "paused": "Paused", "stopped": "Stopped"}


class Controls(QObject):
    """What the desktop can ask of the player. The window connects to these; ``set_state`` goes the other way."""
    play = Signal()
    pause = Signal()
    play_pause = Signal()
    stop = Signal()
    next = Signal()
    previous = Signal()
    raise_window = Signal()
    quit = Signal()
    shuffle = Signal(bool)
    repeat = Signal(str)
    volume = Signal(int)
    open_uri = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.state: dict = {
            "status": "stopped", "title": "", "artist": "", "album": "", "length_us": 0, "track": 0, "url": "",
            "can_next": False, "can_previous": False, "shuffle": False, "repeat": "off", "volume": 1.0,
        }
        self._bus = None
        self._sent: dict = {}
        self._pending: dict[str, set[str]] = {}
        self._flush = QTimer(self)
        self._flush.setSingleShot(True)
        self._flush.setInterval(60)           # one PropertiesChanged for a burst of changes (a new song changes five things)
        self._flush.timeout.connect(self._emit_changes)

    # -- registration -------------------------------------------------------------------------
    def register(self) -> bool:
        """Claim the bus name and publish the object; False on a session without a bus (nothing else is affected)."""
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        # The adaptors hang off a plain QObject, and that object is what gets exported.
        self._holder = QObject(self)
        self._root = _Root(self._holder, self)
        self._player = _Player(self._holder, self)
        if not bus.registerObject(PATH, self._holder):
            return False
        # The first instance is "juke"; a second one gets the pid, as the spec asks for.
        if not bus.registerService(f"org.mpris.MediaPlayer2.{APP_ID}"):
            if not bus.registerService(f"org.mpris.MediaPlayer2.{APP_ID}.instance{os.getpid()}"):
                return False
        self._bus = bus
        self._sent = self._player_values()
        return True

    # -- state from the window ----------------------------------------------------------------------
    def update(self, **values) -> None:
        """Record what changed and tell the desktop, a moment later, in one message."""
        changed = {k for k, v in values.items() if self.state.get(k) != v}
        if not changed:
            return
        self.state.update(values)
        if self._bus is not None:
            self._flush.start()

    def _player_values(self) -> dict:
        p = self._player
        return {"PlaybackStatus": p.PlaybackStatus, "Metadata": p.Metadata, "CanGoNext": p.CanGoNext,
                "CanGoPrevious": p.CanGoPrevious, "Shuffle": p.Shuffle, "LoopStatus": p.LoopStatus,
                "Volume": p.Volume, "CanPlay": p.CanPlay, "CanPause": p.CanPause}

    def _emit_changes(self) -> None:
        now = self._player_values()
        delta = {k: v for k, v in now.items() if self._sent.get(k) != v}
        self._sent = now
        if not delta or self._bus is None:
            return
        message = QDBusMessage.createSignal(PATH, PROPS_IFACE, "PropertiesChanged")
        message.setArguments([PLAYER_IFACE, delta, []])
        self._bus.send(message)

    def unregister(self) -> None:
        if self._bus is not None:
            self._bus.unregisterObject(PATH)
            self._bus.unregisterService(f"org.mpris.MediaPlayer2.{APP_ID}")
            self._bus = None


@ClassInfo({"D-Bus Interface": ROOT_IFACE})
class _Root(QDBusAbstractAdaptor):
    def __init__(self, holder: QObject, controls: Controls) -> None:
        super().__init__(holder)
        self._c = controls

    @Slot()
    def Raise(self) -> None:  # noqa: N802
        self._c.raise_window.emit()

    @Slot()
    def Quit(self) -> None:  # noqa: N802
        self._c.quit.emit()

    @Property(bool, constant=True)
    def CanQuit(self) -> bool:  # noqa: N802
        return True

    @Property(bool, constant=True)
    def CanRaise(self) -> bool:  # noqa: N802
        return True

    @Property(bool, constant=True)
    def HasTrackList(self) -> bool:  # noqa: N802
        return False

    @Property(str, constant=True)
    def Identity(self) -> str:  # noqa: N802
        return "Juke"

    @Property(str, constant=True)
    def DesktopEntry(self) -> str:  # noqa: N802
        return APP_ID

    @Property("QStringList", constant=True)
    def SupportedUriSchemes(self) -> list:  # noqa: N802
        return ["file"]

    @Property("QStringList", constant=True)
    def SupportedMimeTypes(self) -> list:  # noqa: N802
        return ["audio/mpeg", "audio/flac", "audio/ogg", "audio/opus", "audio/mp4", "audio/x-wav"]


@ClassInfo({"D-Bus Interface": PLAYER_IFACE})
class _Player(QDBusAbstractAdaptor):
    def __init__(self, holder: QObject, controls: Controls) -> None:
        super().__init__(holder)
        self._c = controls

    # -- methods
    @Slot()
    def Play(self) -> None:  # noqa: N802
        self._c.play.emit()

    @Slot()
    def Pause(self) -> None:  # noqa: N802
        self._c.pause.emit()

    @Slot()
    def PlayPause(self) -> None:  # noqa: N802
        self._c.play_pause.emit()

    @Slot()
    def Stop(self) -> None:  # noqa: N802
        self._c.stop.emit()

    @Slot()
    def Next(self) -> None:  # noqa: N802
        self._c.next.emit()

    @Slot()
    def Previous(self) -> None:  # noqa: N802
        self._c.previous.emit()

    @Slot(str)
    def OpenUri(self, uri: str) -> None:  # noqa: N802
        self._c.open_uri.emit(uri)

    # -- properties
    @Property(str)
    def PlaybackStatus(self) -> str:  # noqa: N802
        return STATUS.get(self._c.state["status"], "Stopped")

    @Property("QVariantMap")
    def Metadata(self) -> dict:  # noqa: N802
        s = self._c.state
        if s["status"] == "stopped" and not s["title"]:
            return {"mpris:trackid": QDBusObjectPath("/org/mpris/MediaPlayer2/TrackList/NoTrack")}
        data: dict = {"mpris:trackid": QDBusObjectPath(f"/io/github/vezzulab/juke/track/{s['track'] or 0}"),
                      "xesam:title": s["title"]}
        if s["artist"]:
            data["xesam:artist"] = [s["artist"]]
        if s["album"]:
            data["xesam:album"] = s["album"]
        if s["length_us"]:
            data["mpris:length"] = int(s["length_us"])
        if s["url"]:
            data["xesam:url"] = s["url"]
        return data

    @Property(bool)
    def CanGoNext(self) -> bool:  # noqa: N802
        return bool(self._c.state["can_next"])

    @Property(bool)
    def CanGoPrevious(self) -> bool:  # noqa: N802
        return bool(self._c.state["can_previous"])

    @Property(bool, constant=True)
    def CanPlay(self) -> bool:  # noqa: N802
        return True

    @Property(bool, constant=True)
    def CanPause(self) -> bool:  # noqa: N802
        return True

    @Property(bool, constant=True)
    def CanSeek(self) -> bool:  # noqa: N802
        return False

    @Property(bool, constant=True)
    def CanControl(self) -> bool:  # noqa: N802
        return True

    def _set_shuffle(self, value: bool) -> None:
        self._c.shuffle.emit(bool(value))

    Shuffle = Property(bool, lambda self: bool(self._c.state["shuffle"]), _set_shuffle)

    def _set_loop(self, value: str) -> None:
        self._c.repeat.emit(LOOP_BACK.get(value, "off"))

    LoopStatus = Property(str, lambda self: LOOP.get(self._c.state["repeat"], "None"), _set_loop)

    def _set_volume(self, value: float) -> None:
        self._c.volume.emit(max(0, min(100, int(round(float(value) * 100)))))

    Volume = Property(float, lambda self: float(self._c.state["volume"]), _set_volume)

    @Property(float, constant=True)
    def Rate(self) -> float:  # noqa: N802
        return 1.0

    @Property(float, constant=True)
    def MinimumRate(self) -> float:  # noqa: N802
        return 1.0

    @Property(float, constant=True)
    def MaximumRate(self) -> float:  # noqa: N802
        return 1.0
