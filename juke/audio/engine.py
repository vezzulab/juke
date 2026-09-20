"""Audio engine: one long-lived libVLC media player.

The same MediaPlayer (and therefore the same audio pipeline and equalizer)
serves every track: changing songs only swaps the media, so the equalizer
setting is never torn down between tracks.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .balance import StreamBalance
from .equalizer import BANDS_HZ, Equalizer

try:
    import vlc
    VLC_ERROR: str | None = None
except (ImportError, OSError) as exc:  # python-vlc missing or libvlc.so not installed
    vlc = None
    VLC_ERROR = str(exc)

POLL_MS = 250
READY_AFTER_MS = 400  # media time after which the audio output is fully up


def _pulse_plugin_present() -> bool:
    """Is VLC's PulseAudio output installed? (PipeWire desktops serve it through pipewire-pulse.)"""
    roots = [Path(p) for p in os.environ.get("VLC_PLUGIN_PATH", "").split(os.pathsep) if p]
    roots += [Path(p) for pattern in ("/usr/lib*/vlc/plugins", "/usr/lib/*-linux-gnu/vlc/plugins", "/usr/local/lib*/vlc/plugins")
              for p in glob.glob(pattern)]
    return any((root / "audio_output" / "libpulse_plugin.so").is_file() for root in roots)


class AudioEngine(QObject):
    state_changed = Signal(str)                # "playing" | "paused" | "stopped"
    position_changed = Signal(int, int)        # elapsed ms, total ms
    track_finished = Signal()                  # reached the end by itself
    error = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.available = vlc is not None
        self.rate = 1.0
        self.balance = 0.0
        self.volume = 80
        self.muted = False
        self._state = "stopped"
        self.unavailable_reason = ""
        self._balance_dirty = False
        self._equalizer: Equalizer | None = None
        self._vlc_eq = None                    # keep the native equalizer alive
        self._instance = None
        self._player = None
        self._balance = StreamBalance()
        self.balance_supported = self._balance.supported
        # libVLC 3's PipeWire output crashes if volume/mute are touched before its stream
        # exists, while the PulseAudio output has no such problem. Prefer pulse when
        # installed; otherwise hold volume/mute back until audio is really flowing.
        self._aout_safe = self.available and _pulse_plugin_present()
        self._audio_ready = self._aout_safe
        self._audio_pending = False
        if self.available:
            try:
                args = ["--no-video", "--quiet", "--no-metadata-network-access", "--no-snapshot-preview",
                        "--http-user-agent=Juke"]
                if self._aout_safe:
                    args.append("--aout=pulse,any")
                self._instance = vlc.Instance(*args)
                self._player = self._instance.media_player_new()
            except Exception as exc:  # libvlc present but unusable (no plugins...)
                self.available = False
                self._instance = self._player = None
                self.unavailable_reason = str(exc)
        if not self.available and not self.unavailable_reason:
            self.unavailable_reason = VLC_ERROR or "libVLC not found"
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # -- playback ----------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    def play_url(self, url: str) -> bool:
        """Start ``url`` (file:///... or http(s)://...) on the same player."""
        if not self.available:
            self.error.emit(self.unavailable_reason)
            return False
        media = self._instance.media_new_location(url)
        if url.startswith(("http://", "https://")):
            media.add_option(":network-caching=2000")
        self._player.set_media(media)
        media.release()
        self._player.play()
        self._audio_ready = self._aout_safe
        self._audio_pending = True
        self._apply_audio_levels()
        self._player.set_rate(self.rate)
        self._apply_equalizer()          # idempotent: the pipeline is not restarted
        self._set_state("playing")
        self._schedule_balance()
        return True

    def toggle_pause(self) -> None:
        if not self.available or self._state == "stopped":
            return
        self._player.pause()
        self._set_state("paused" if self._state == "playing" else "playing")

    def pause(self) -> None:
        if self.available and self._state == "playing":
            self._player.set_pause(1)
            self._set_state("paused")

    def resume(self) -> None:
        if self.available and self._state == "paused":
            self._player.set_pause(0)
            self._set_state("playing")

    def stop(self) -> None:
        if self.available:
            self._player.stop()
        self._set_state("stopped")
        self.position_changed.emit(0, 0)

    def seek(self, fraction: float) -> None:
        if not self.available or self._state == "stopped":
            return
        length = self._player.get_length()
        fraction = max(0.0, min(1.0, fraction))
        if length > 0:
            self._player.set_time(int(length * fraction))
        else:
            self._player.set_position(fraction)

    def position_ms(self) -> int:
        return max(0, self._player.get_time()) if self.available else 0

    # -- audio settings ------------------------------------------------------------
    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        self._audio_pending = True
        self._apply_audio_levels()
        self._schedule_balance()  # libVLC rewrites channel volumes when the level changes

    def set_muted(self, muted: bool) -> None:
        self.muted = bool(muted)
        self._audio_pending = True
        self._apply_audio_levels()

    def _apply_audio_levels(self) -> None:
        """Push volume/mute to libVLC as soon as it is safe to do so (see __init__)."""
        if not self.available or not self._audio_ready or not self._audio_pending:
            return
        self._player.audio_set_volume(self.volume)
        self._player.audio_set_mute(self.muted)
        self._audio_pending = False

    def set_rate(self, rate: float) -> None:
        self.rate = max(0.5, min(2.0, float(rate)))
        if self.available:
            self._player.set_rate(self.rate)

    def set_balance(self, balance: float) -> None:
        self.balance = max(-1.0, min(1.0, float(balance)))
        self._schedule_balance()

    def _schedule_balance(self) -> None:
        if self.available and self._balance.supported and self._state != "stopped":
            # the sink input appears a moment after playback starts, and volume
            # changes reset it: apply shortly afterwards
            QTimer.singleShot(150, self._apply_balance)
            QTimer.singleShot(900, self._apply_balance)

    def _apply_balance(self) -> None:
        if self._state != "stopped" and (self.balance != 0.0 or self._balance_dirty):
            self._balance.apply(self.balance)
            self._balance_dirty = self.balance != 0.0

    def attach_equalizer(self, equalizer: Equalizer) -> None:
        self._equalizer = equalizer
        equalizer.changed.connect(self._apply_equalizer)
        self._apply_equalizer()

    def _apply_equalizer(self) -> None:
        """Push the current curve to libVLC (live, without touching playback)."""
        if not self.available or self._equalizer is None:
            return
        eq = self._equalizer
        if not eq.enabled:
            self._player.set_equalizer(None)
            self._vlc_eq = None
            return
        native = vlc.AudioEqualizer()
        native.set_preamp(eq.preamp)
        for band, gain in enumerate(eq.gains):
            native.set_amp_at_index(gain, band)
        self._player.set_equalizer(native)
        self._vlc_eq = native

    # -- housekeeping ------------------------------------------------------------------
    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)

    def _poll(self) -> None:
        if not self.available or self._state == "stopped":
            return
        vlc_state = self._player.get_state()
        if vlc_state == vlc.State.Ended:
            self._set_state("stopped")
            self.position_changed.emit(0, 0)
            self.track_finished.emit()
        elif vlc_state == vlc.State.Error:
            self._set_state("stopped")
            self.error.emit("playback error")
        elif self._state == "playing":
            if not self._audio_ready and self._player.get_time() >= READY_AFTER_MS:
                self._audio_ready = True
                self._apply_audio_levels()
            self.position_changed.emit(max(0, self._player.get_time()), max(0, self._player.get_length()))

    def shutdown(self) -> None:
        self._timer.stop()
        if self.available and self._player is not None:
            self._player.stop()
            self._player.release()
            self._instance.release()
            self._player = None
            self.available = False


assert len(BANDS_HZ) == 10  # libVLC's equalizer always has exactly 10 bands
