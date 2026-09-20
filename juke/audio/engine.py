"""Audio engine: one long-lived libVLC media player, created only when something is played.

Keeping libVLC out of the process until the first Play saves ~10 MB and its start-up work, and the
poll timer only exists while a song is playing or paused, so an idle Juke never wakes the CPU.

The same MediaPlayer (and therefore the same audio pipeline and equalizer) serves every track:
changing songs only swaps the media, so the equalizer setting is never torn down between tracks.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from ..workers import AsyncWorker
from . import icy
from .balance import StreamBalance
from .equalizer import BANDS_HZ, Equalizer

POLL_ACTIVE_MS = 500     # window in front: progress bar and time labels follow playback
ICY_FIRST_MS = 2500      # first own ICY title lookup after tuning in
ICY_EVERY_MS = 30_000    # then every half minute, and only while the window is in front
POLL_HIDDEN_MS = 2000    # window hidden/minimised/unfocused: only watch for the end of the song
READY_AFTER_MS = 400     # media time after which the audio output is fully up


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
    now_playing_changed = Signal(str)          # live radio: the song the station is playing right now (ICY metadata)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rate = 1.0
        self.balance = 0.0
        self.volume = 80
        self.muted = False
        self.unavailable_reason = ""
        self._state = "stopped"
        self._equalizer: Equalizer | None = None
        self._vlc_eq = None                    # keep the native equalizer alive
        self._vlc = None                       # the python-vlc module, imported on first use
        self._instance = None
        self._player = None
        self._media = None                     # the media being played: libVLC updates its metadata live
        self._live = False
        self._url_leaf = ""
        self._url = ""
        self._icy_token = 0
        self._icy_worker: AsyncWorker | None = None
        self._station_name = ""
        self._now_playing = ""
        self._backend_tried = False
        self._balance_dirty = False
        self._balance = StreamBalance()
        self.balance_supported = self._balance.supported
        self._aout_safe = False
        self._audio_ready = False
        self._audio_pending = True
        self._ui_active = True
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.CoarseTimer)   # lets the kernel batch our wake-ups with others
        self._timer.setInterval(POLL_ACTIVE_MS)
        self._timer.timeout.connect(self._poll)

    # -- lazy libVLC ----------------------------------------------------------------------
    def _ensure_backend(self) -> bool:
        if self._backend_tried:
            return self._player is not None
        self._backend_tried = True
        try:
            import vlc
        except (ImportError, OSError) as exc:  # python-vlc missing or libvlc.so not installed
            self.unavailable_reason = str(exc) or "libVLC not found"
            return False
        # libVLC 3's PipeWire output crashes if volume/mute are touched before its stream exists,
        # while the PulseAudio output has no such problem. Prefer pulse when installed; otherwise
        # hold volume/mute back until audio is really flowing.
        self._aout_safe = _pulse_plugin_present()
        self._audio_ready = self._aout_safe
        args = ["--no-video", "--quiet", "--no-metadata-network-access", "--no-snapshot-preview",
                "--http-user-agent=Juke"]
        if self._aout_safe:
            args.append("--aout=pulse,any")
        try:
            self._instance = vlc.Instance(*args)
            self._player = self._instance.media_player_new()
        except Exception as exc:  # libvlc present but unusable (no plugins...)
            self.unavailable_reason = str(exc) or "libVLC could not start"
            self._instance = self._player = None
            return False
        self._vlc = vlc
        self._player.set_rate(self.rate)
        self._audio_pending = True
        self._apply_audio_levels()
        self._apply_equalizer()
        return True

    @property
    def available(self) -> bool:
        return self._ensure_backend()

    # -- playback ----------------------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    def play_url(self, url: str) -> bool:
        """Start ``url`` (file:///... or http(s)://...) on the same player."""
        if not self._ensure_backend():
            self.error.emit(self.unavailable_reason)
            return False
        media = self._instance.media_new_location(url)
        if url.startswith(("http://", "https://")):
            media.add_option(":network-caching=2000")
        self._player.set_media(media)
        old, self._media = self._media, media       # keep it: ICY "now playing" arrives on this object
        if old is not None:
            old.release()
        self._now_playing = ""
        self._url_leaf = os.path.basename(url.split("?", 1)[0].rstrip("/")).lower()
        self._url = url
        self._player.play()
        self._audio_ready = self._aout_safe
        self._audio_pending = True
        self._apply_audio_levels()
        self._player.set_rate(self.rate)
        self._apply_equalizer()          # idempotent: the pipeline is not restarted
        self._set_state("playing")
        self._schedule_balance()
        self._icy_token += 1
        if self._live:
            self._later(ICY_FIRST_MS, lambda t=self._icy_token: self._lookup_title(t))
        return True

    def set_live(self, live: bool, station_name: str = "") -> None:
        """Live radio: while on, ICY "now playing" metadata is read and announced as it changes."""
        self._live = live
        self._station_name = station_name
        if not live:
            self._now_playing = ""

    def now_playing(self) -> str:
        return self._now_playing

    # -- our own ICY lookup (libVLC does not request titles on https streams) ----------------------
    def _lookup_title(self, token: int) -> None:
        """Chain of single-shot timers: it ends by itself when the station is left or stopped."""
        if token != self._icy_token or not self._live or self._state == "stopped":
            return
        again = lambda: self._later(ICY_EVERY_MS, lambda: self._lookup_title(token))
        if not self._ui_active or self._read_now_playing():        # nobody is looking / libVLC already has it
            again()
            return
        url = self._url

        async def look(_progress):
            return await icy.read_stream_title(url)

        worker = AsyncWorker(look, self)
        self._icy_worker = worker

        def done(raw: str) -> None:
            if token == self._icy_token and self._live:
                self._announce(icy.clean_stream_title(raw, self._station_name))
            again()

        worker.result.connect(done)
        worker.failed.connect(lambda _m: again())
        worker.finished.connect(lambda w=worker: (setattr(self, "_icy_worker", None) if self._icy_worker is w else None, w.deleteLater()))
        worker.start()

    def _later(self, ms: int, callback) -> None:
        """A single-shot timer on the kernel-friendly coarse clock (QTimer.singleShot cannot pick one)."""
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setTimerType(Qt.VeryCoarseTimer)
        timer.timeout.connect(callback)
        timer.timeout.connect(timer.deleteLater)
        timer.start(ms)

    def _announce(self, text: str) -> None:
        if text != self._now_playing:
            self._now_playing = text
            self.now_playing_changed.emit(text)

    def _read_now_playing(self) -> str:
        media, vlc = self._media, self._vlc
        if media is None or vlc is None:
            return ""
        text = media.get_meta(vlc.Meta.NowPlaying) or ""
        if not text:                                           # Ogg/Vorbis streams carry artist and title instead
            title, artist = media.get_meta(vlc.Meta.Title) or "", media.get_meta(vlc.Meta.Artist) or ""
            if title and self._is_real_title(title):
                text = f"{artist} - {title}" if artist else title
        return " ".join(text.split())

    def _is_real_title(self, title: str) -> bool:
        """libVLC fills "title" with the station name or, failing that, the last part of the address
        ("stream", "live.mp3"): neither is a song."""
        low = title.strip().lower()
        if not low or low == self._station_name.strip().lower() or low.startswith(("http://", "https://")):
            return False
        return low != self._url_leaf and low != os.path.splitext(self._url_leaf)[0]

    def toggle_pause(self) -> None:
        if self._player is None or self._state == "stopped":
            return
        self._player.pause()
        self._set_state("paused" if self._state == "playing" else "playing")

    def pause(self) -> None:
        if self._player is not None and self._state == "playing":
            self._player.set_pause(1)
            self._set_state("paused")

    def resume(self) -> None:
        if self._player is not None and self._state == "paused":
            self._player.set_pause(0)
            self._set_state("playing")

    def stop(self) -> None:
        self._now_playing = ""
        if self._player is not None:
            self._player.stop()
        self._set_state("stopped")
        self.position_changed.emit(0, 0)

    def seek(self, fraction: float) -> None:
        if self._player is None or self._state == "stopped":
            return
        length = self._player.get_length()
        fraction = max(0.0, min(1.0, fraction))
        if length > 0:
            self._player.set_time(int(length * fraction))
        else:
            self._player.set_position(fraction)

    def position_ms(self) -> int:
        return max(0, self._player.get_time()) if self._player is not None else 0

    # -- audio settings --------------------------------------------------------------------------
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
        """Push volume/mute to libVLC as soon as it is safe to do so (see _ensure_backend)."""
        if self._player is None or not self._audio_ready or not self._audio_pending:
            return
        self._player.audio_set_volume(self.volume)
        self._player.audio_set_mute(self.muted)
        self._audio_pending = False

    def set_rate(self, rate: float) -> None:
        self.rate = max(0.5, min(2.0, float(rate)))
        if self._player is not None:
            self._player.set_rate(self.rate)

    def set_balance(self, balance: float) -> None:
        self.balance = max(-1.0, min(1.0, float(balance)))
        self._schedule_balance()

    def _schedule_balance(self) -> None:
        if self._player is not None and self._balance.supported and self._state != "stopped":
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
        if self._player is None or self._equalizer is None:
            return
        eq = self._equalizer
        if not eq.enabled:
            self._player.set_equalizer(None)
            self._vlc_eq = None
            return
        native = self._vlc.AudioEqualizer()
        native.set_preamp(eq.preamp)
        for band, gain in enumerate(eq.gains):
            native.set_amp_at_index(gain, band)
        self._player.set_equalizer(native)
        self._vlc_eq = native

    # -- housekeeping ------------------------------------------------------------------------------
    def set_ui_active(self, active: bool) -> None:
        """Window in front? Nobody is watching the progress bar otherwise, so poll less often."""
        if active == self._ui_active:
            return
        self._ui_active = active
        self._timer.setInterval(POLL_ACTIVE_MS if active else POLL_HIDDEN_MS)
        if active and self._state != "stopped":
            self._poll()

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            if state == "stopped":
                self._timer.stop()             # nothing to watch: no wake-ups at all
            elif not self._timer.isActive():
                self._timer.start()
            self.state_changed.emit(state)
        elif state != "stopped" and not self._timer.isActive():
            self._timer.start()

    def _poll(self) -> None:
        if self._player is None or self._state == "stopped":
            return
        vlc = self._vlc
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
            if self._live:
                text = self._read_now_playing()          # libVLC's own reading (http:// streams)
                if text and text != self._now_playing:
                    self._announce(text)
            if self._ui_active:
                self.position_changed.emit(max(0, self._player.get_time()), max(0, self._player.get_length()))

    def shutdown(self) -> None:
        self._icy_token += 1
        if self._icy_worker is not None:
            self._icy_worker.cancel()
            self._icy_worker.wait(1500)
        self._timer.stop()
        if self._player is not None:
            self._player.stop()
            self._player.release()
            if self._media is not None:
                self._media.release()
                self._media = None
            self._instance.release()
            self._player = None


assert len(BANDS_HZ) == 10  # libVLC's equalizer always has exactly 10 bands
