"""Media keys and the Now Playing widget on a Mac.

macOS hands the play / pause / next / previous keys of a keyboard or a headset to the app that says it is the one playing
(``MPRemoteCommandCenter``), and it shows what is playing in Control Center and on the lock screen from what the app
publishes (``MPNowPlayingInfoCenter``). This is the Mac's counterpart of ``mpris``: the window talks to it through the
same ``Controls`` object, so it does not know which one it has. Nothing polls; the system calls us, and we only speak
when something changed.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QObject, Signal

from .mpris import Controls as _Controls

log = logging.getLogger("juke")


class _Relay(QObject):
    """The system may call from any thread; the window must hear it on the Qt thread."""
    command = Signal(str)


class Controls(_Controls):
    """Same signals and ``update()`` as ``mpris.Controls``; ``register()`` claims the media keys instead of a bus name."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mp = None                       # the MediaPlayer framework, once it has loaded
        self._targets: list = []
        self._relay = _Relay(self)
        self._relay.command.connect(self._run, Qt.QueuedConnection)

    # -- registration -------------------------------------------------------------------------
    def register(self) -> bool:
        try:
            import MediaPlayer as mp
        except ImportError:
            return False
        self._mp = mp
        center = mp.MPRemoteCommandCenter.sharedCommandCenter()
        for name, command in (("play", center.playCommand()), ("pause", center.pauseCommand()),
                              ("play_pause", center.togglePlayPauseCommand()), ("stop", center.stopCommand()),
                              ("next", center.nextTrackCommand()), ("previous", center.previousTrackCommand())):
            command.setEnabled_(True)
            self._targets.append((command, command.addTargetWithHandler_(self._handler(name))))
        self._bus = True                      # (what ``update()`` checks before it tells anyone)
        self._emit_changes()
        return True

    def _handler(self, name: str):
        def handle(_event) -> int:
            self._relay.command.emit(name)
            return self._mp.MPRemoteCommandHandlerStatusSuccess
        return handle

    def _run(self, name: str) -> None:
        getattr(self, name).emit()

    def unregister(self) -> None:
        for command, target in self._targets:
            command.removeTarget_(target)
        self._targets = []
        if self._mp is not None:
            info = self._mp.MPNowPlayingInfoCenter.defaultCenter()
            info.setNowPlayingInfo_(None)
            info.setPlaybackState_(self._mp.MPNowPlayingPlaybackStateStopped)
        self._bus = None

    # -- what is playing ----------------------------------------------------------------------------
    def _emit_changes(self) -> None:
        mp, s = self._mp, self.state
        if mp is None or self._bus is None:
            return
        center = mp.MPNowPlayingInfoCenter.defaultCenter()
        if s["status"] == "stopped" and not s["title"]:
            center.setNowPlayingInfo_(None)
            center.setPlaybackState_(mp.MPNowPlayingPlaybackStateStopped)
            return
        info = {mp.MPMediaItemPropertyTitle: s["title"],
                mp.MPNowPlayingInfoPropertyPlaybackRate: 1.0 if s["status"] == "playing" else 0.0}
        if s["artist"]:
            info[mp.MPMediaItemPropertyArtist] = s["artist"]
        if s["album"]:
            info[mp.MPMediaItemPropertyAlbumTitle] = s["album"]
        if s["length_us"]:
            info[mp.MPMediaItemPropertyPlaybackDuration] = s["length_us"] / 1_000_000
        center.setNowPlayingInfo_(info)
        center.setPlaybackState_({"playing": mp.MPNowPlayingPlaybackStatePlaying,
                                  "paused": mp.MPNowPlayingPlaybackStatePaused}.get(s["status"], mp.MPNowPlayingPlaybackStateStopped))
