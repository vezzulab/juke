"""10-band graphic equalizer state, built-in and user presets.

The bands are the fixed ones libVLC exposes (``libvlc_audio_equalizer_get_band_frequency``);
gains and preamp are in dB within libVLC's ±20 dB range.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal

from ..config import Config

BANDS_HZ = (60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000)
BAND_LABELS = ("60", "170", "310", "600", "1K", "3K", "6K", "12K", "14K", "16K")
# What each band changes, in plain words: (group, name, what it is, what too much does). The texts are in the locales as
# "eq.band.<hz>.name" / ".about" and "eq.group.<group>".
BAND_GROUPS = ("bass", "bass", "bass", "mids", "mids", "mids", "treble", "treble", "treble", "treble")
MIN_DB = -20.0
MAX_DB = 20.0

# name -> gains for BANDS_HZ (dB). The curves are deliberately smooth: neighbouring bands never jump more than a few
# dB, because a jagged curve sounds phasey rather than better. Every preset is played with the preamp of
# ``headroom()`` below, so a boost never drives the signal into clipping.
BUILTIN_PRESETS: dict[str, tuple[float, ...]] = {
    "Flat":        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "Rock":        (5, 4, 1, -1, -1, 2, 4, 4, 4, 3),
    "Pop":         (3, 2, 0, 0, 1, 3, 3, 3, 3, 2),
    "Jazz":        (3, 2, 1, 0, 0, 1, 2, 2, 2, 2),
    "Bass Boost":  (8, 6, 4, 2, 0, 0, 0, 0, 0, 0),
    "Vocal":       (-3, -2, -1, 1, 3, 4, 3, 1, 1, 0),
    "Classical":   (2, 1, 0, 0, 0, 1, 1, 2, 2, 2),
    "Electronic":  (6, 5, 2, 0, -1, 1, 3, 4, 4, 4),
    "Heavy Metal": (5, 4, 1, -1, 0, 3, 4, 4, 4, 3),
    "Techno":      (6, 5, 2, -1, -2, 1, 3, 4, 5, 4),
    # Caribbean genres, each tuned for what actually carries it: the sub kick of dembow and reggaeton, the brass and
    # timbales of salsa, the tambora and güira of merengue, the requinto guitar of bachata.
    "Dembow":      (7, 5, 2, -1, 0, 2, 4, 4, 4, 3),
    "Reggaeton":   (6, 5, 2, 0, 1, 2, 3, 3, 3, 2),
    "Salsa":       (2, 2, 0, 1, 2, 3, 4, 3, 3, 2),
    "Merengue":    (4, 3, 0, 1, 2, 3, 4, 4, 4, 3),
    "Bachata":     (3, 2, -1, 0, 2, 4, 4, 3, 3, 2),
    # Everyday listening: a preset for the speaker or the room, a few for the way the music is mixed.
    "Loudness": (6, 4, 1, 0, 0, 0, 1, 3, 4, 4),
    "Bass Reducer": (-6, -4, -2, 0, 0, 0, 0, 0, 0, 0),
    "Treble Boost": (0, 0, 0, 0, 0, 1, 3, 5, 6, 6),
    "Treble Reducer": (0, 0, 0, 0, 0, 0, -2, -4, -6, -6),
    "Hip-Hop": (6, 5, 2, 0, 0, 1, 1, 2, 2, 2),
    "R&B": (5, 4, 2, 0, 1, 2, 1, 1, 2, 2),
    "Dance": (6, 5, 3, 0, 0, 1, 2, 3, 3, 2),
    "Acoustic": (3, 2, 1, 1, 1, 2, 3, 3, 3, 2),
    "Latin": (4, 3, 1, 0, 1, 3, 4, 4, 3, 2),
    "Cumbia": (4, 3, 1, 0, 2, 3, 3, 3, 2, 1),
    "Afrobeat": (5, 4, 2, 0, 1, 2, 3, 3, 3, 2),
    "Reggae": (4, 3, 0, -2, -1, 1, 3, 3, 2, 2),
    "K-Pop": (4, 3, 1, 0, 2, 4, 4, 3, 3, 2),
    "Country": (2, 1, 1, 1, 2, 3, 3, 3, 2, 1),
    "Blues": (3, 2, 1, 0, 0, 1, 2, 2, 1, 0),
    "Speech": (-4, -3, -1, 1, 3, 4, 3, 0, -2, -3),
    "Night": (-3, -2, 0, 1, 2, 2, 1, 0, -1, -2),
    "Small Speakers": (6, 5, 3, 1, 0, 0, 1, 2, 2, 2),
    "Headphones": (3, 3, 2, 0, -1, -1, 0, 2, 3, 3),
    "Live": (-2, 0, 2, 3, 3, 3, 2, 2, 2, 1),
}


# Where and how you listen: name -> dB added on top of whatever curve is set, so your own curves are never replaced.
# A graphic equalizer cannot remove a real echo; the small-room curve takes down the low-mids that boom and the harsh
# highs that bounce, which is what makes a small room sound echoey. The surround ones are for Juke's stereo going
# through a 5.1 / 7.1 receiver: the subwoofer already carries the bass, so less of it here.
SETUPS: dict[str, tuple[float, ...]] = {
    "Small Room":      (-2, -3, -3, -1, 0, 1, 0, -1, -2, -2),
    "Small Speakers":  (4, 4, 2, 1, 0, 0, 1, 2, 2, 2),
    "Medium Speakers": (2, 2, 1, 1, 0, 0, 1, 1, 2, 2),
    "Large Speakers":  (-2, -1, 0, 0, 0, 1, 1, 2, 2, 2),
    "Headphones":      (3, 3, 2, 0, -1, -1, 0, 2, 3, 3),
    "Surround 5.1":    (-3, -2, -1, 0, 0, 1, 1, 2, 2, 2),
    "Surround 7.1":    (-3, -2, -1, 0, 0, 1, 2, 2, 3, 3),
}


# The advanced controls, each a shape that is added to the curve in proportion to its slider (0-100 %). They are for
# the places where echo and reverb are heard: the low-mid boom that rooms pile up, the long tail of bright highs, the
# presence that keeps the direct sound ahead of the room, and bass that is tight instead of one long note. They shape
# the sound; they cannot take a real echo or reverb out of a recording.
ADVANCED: dict[str, tuple[float, ...]] = {
    "echo":    (-1, -3, -5, -5, -2, 0, 0, 0, 0, 0),
    "reverb":  (0, 0, 0, 0, 0, 0, -2, -4, -5, -5),
    "clarity": (0, 0, 0, 0, 1, 3, 4, 2, 0, 0),
    "tight":   (1, 0, -3, -2, 0, 0, 0, 0, 0, 0),
    "shrill":  (0, 0, 0, 0, -1, -4, -5, -2, 0, 0),
}
ADVANCED_LEVELS = {"room": (50, 75, 100, 125, 150), "echo": (0, 25, 50, 75, 100), "reverb": (0, 25, 50, 75, 100),
                   "clarity": (0, 25, 50, 75, 100), "tight": (0, 25, 50, 75, 100),
                   "shrill": (0, 25, 50, 75, 100)}   # the buttons of the advanced deck
ADVANCED_DEFAULT = {"room": 100, "echo": 0, "reverb": 0, "clarity": 0, "tight": 0, "shrill": 0}   # room: how much of the setup to use


def headroom(gains) -> float:
    """The preamp a curve has to be played at so that its loudest boost cannot clip.

    A song is already mastered close to the maximum, so lifting a band by +7 dB has nowhere to go and the sound
    breaks up — the opposite of what the boost was for. Shifting the whole curve down by its own biggest boost keeps
    the shape and the headroom; what is lost is loudness, which the volume knob gives back cleanly.
    """
    return -max(0.0, max(gains))


def _clamp(value: float) -> float:
    return max(MIN_DB, min(MAX_DB, float(value)))


class Equalizer(QObject):
    """Holds the current curve; ``changed`` fires after every edit."""

    changed = Signal()
    song_cleared = Signal(int)          # the person went back to the general equalizer for the song that is playing

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.song_id: int | None = None                    # set while the song that plays has an equalizer of its own
        self.song_saver = None                             # callable(song id, curve): where edits of that curve are kept
        self._general: tuple | None = None                 # the general curve, put away while a song's own plays
        state = config.get("equalizer")
        self.enabled: bool = bool(state["enabled"])
        self.preamp: float = _clamp(state["preamp"])
        self.gains: list[float] = [_clamp(g) for g in state["gains"]]
        self.preset: str | None = state["preset"]
        self.origin: str | None = self.preset              # the preset the curve in play came from, even after a bar moved
        stored = config.get("advanced_eq", {})
        self.advanced: dict[str, int] = {
            k: max(0, min(150 if k == "room" else 100, int(stored.get(k, d)))) if isinstance(stored, dict) else d
            for k, d in ADVANCED_DEFAULT.items()}
        saved = config.get("listening_setup", None)
        self.setup: str | None = saved if saved in SETUPS else None
        self.custom: dict[str, dict] = {
            name: {"preamp": _clamp(p["preamp"]), "gains": [_clamp(g) for g in p["gains"]]}
            for name, p in config.get("custom_presets", {}).items()
            if isinstance(p, dict) and len(p.get("gains", [])) == 10
        }

    # -- state ---------------------------------------------------------------
    def _persist(self) -> None:
        if self.song_id is not None:                       # editing a song's own curve: it is kept with the song, not as the general one
            if self.song_saver is not None:
                self.song_saver(self.song_id, self.song_curve())
            self._config.set("custom_presets", self.custom)
            return
        self._config.set("equalizer", {
            "enabled": self.enabled, "preamp": self.preamp,
            "gains": list(self.gains), "preset": self.preset,
        })
        self._config.set("custom_presets", self.custom)

    def _emit(self) -> None:
        self._persist()
        self.changed.emit()

    def set_setup(self, name: str | None) -> None:
        """Choose where/how you listen (None = nothing added); it is added to the curve, which stays as it is."""
        self.setup = name if name in SETUPS else None
        if self.setup is not None:
            self.enabled = True
        self._config.set("listening_setup", self.setup)
        self._emit()

    def set_advanced(self, key: str, value: int) -> None:
        """One advanced control (``room`` 0-150 %, the others 0-100 %); moving one away from its rest turns the
        equalizer on."""
        if key not in ADVANCED_DEFAULT:
            return
        self.advanced[key] = max(0, min(150 if key == "room" else 100, int(value)))
        if self.advanced[key] != ADVANCED_DEFAULT[key]:
            self.enabled = True
        self._config.set("advanced_eq", dict(self.advanced))
        self._emit()

    def reset_advanced(self) -> None:
        self.advanced = dict(ADVANCED_DEFAULT)
        self._config.set("advanced_eq", dict(self.advanced))
        self._emit()

    def setup_offsets(self) -> list[float]:
        """What is added on top of the curve for each band: the listening setup (scaled by ``room``) plus the
        advanced controls. All zeros for Normal with the advanced controls at rest."""
        base = SETUPS.get(self.setup, (0.0,) * 10)
        out = [b * self.advanced["room"] / 100 for b in base]
        for key, shape in ADVANCED.items():
            amount = self.advanced[key] / 100
            out = [o + s * amount for o, s in zip(out, shape)]
        return out

    def setup_preamp_offset(self) -> float:
        """What the listening setup adds to the preamp (it only ever lowers it)."""
        return -max(0.0, max(self.setup_offsets()))

    def effective_gains(self) -> list[float]:
        """The curve that is actually played: yours plus the listening setup."""
        return [_clamp(g + e) for g, e in zip(self.gains, self.setup_offsets())]

    def effective_preamp(self) -> float:
        """The preamp, lowered by the biggest boost the setup adds so that it cannot clip."""
        return _clamp(self.preamp + self.setup_preamp_offset())

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self._emit()

    def set_preamp(self, db: float) -> None:
        self.preamp = _clamp(db)
        self.preset = self._matching_preset()
        self._emit()

    def set_band(self, index: int, db: float) -> None:
        self.gains[index] = _clamp(db)
        self.preset = self._matching_preset()
        self._emit()

    def _matching_preset(self) -> str | None:
        for name, (preamp, gains) in self._all_presets().items():
            if abs(preamp - self.preamp) < 0.05 and all(abs(a - b) < 0.05 for a, b in zip(gains, self.gains)):
                return name
        return None

    # -- presets ---------------------------------------------------------------
    def _all_presets(self) -> dict[str, tuple[float, tuple[float, ...]]]:
        presets = {name: (headroom(gains), tuple(map(float, gains))) for name, gains in BUILTIN_PRESETS.items()}
        for name, p in self.custom.items():
            presets[name] = (p["preamp"], tuple(p["gains"]))
        return presets

    def preset_names(self) -> list[str]:
        return list(BUILTIN_PRESETS) + sorted(self.custom, key=str.casefold)

    def is_builtin(self, name: str) -> bool:
        return name in BUILTIN_PRESETS

    def load_preset(self, name: str) -> None:
        presets = self._all_presets()
        if name not in presets:
            return
        self.preamp, gains = presets[name]
        self.gains = list(gains)
        self.preset = name
        self.origin = name
        self._emit()

    def save_custom(self, name: str) -> bool:
        """Store the current curve under ``name``; built-in names are protected."""
        name = name.strip()
        if not name or name in BUILTIN_PRESETS:
            return False
        self.custom[name] = {"preamp": self.preamp, "gains": list(self.gains)}
        self.preset = name
        self.origin = name
        self._emit()
        return True

    def update_preset(self) -> bool:
        """Keep the curve in play in the preset it came from too (only presets of your own can change)."""
        name = self.origin
        if name not in self.custom:
            return False
        self.preset = self._matching_preset()
        self.custom[name] = {"preamp": self.preamp, "gains": list(self.gains)}
        self._emit()
        return True

    def delete_custom(self, name: str) -> bool:
        if name not in self.custom:
            return False
        del self.custom[name]
        if self.preset == name:
            self.preset = self._matching_preset()
        self._emit()
        return True

    def reset(self) -> None:
        self.load_preset("Flat")

    # -- a song's own equalizer ---------------------------------------------------------------------------
    def song_curve(self) -> dict:
        """The curve in play as something to keep with a song."""
        return {"name": self.preset or "", "preamp": self.preamp, "gains": list(self.gains)}

    @staticmethod
    def parse_curve(text: str) -> dict | None:
        """A song's saved curve, or None when it has none (or the text is not a usable curve)."""
        if not text:
            return None
        try:
            data = json.loads(text)
            gains = [_clamp(g) for g in data["gains"]]
            if len(gains) != 10:
                return None
            return {"name": str(data.get("name") or ""), "preamp": _clamp(data.get("preamp", 0.0)), "gains": gains}
        except (ValueError, KeyError, TypeError):
            return None

    def curve_for(self, preset: str) -> dict | None:
        """A preset (built-in or yours) as a curve to give a song."""
        presets = self._all_presets()
        if preset not in presets:
            return None
        preamp, gains = presets[preset]
        return {"name": preset, "preamp": preamp, "gains": list(gains)}

    def begin_song(self, song_id: int, curve: dict | None) -> None:
        """A song starts. With a curve of its own, that is what plays (and what the sliders edit) until the song
        changes; without one, the general equalizer."""
        had = self.song_id is not None
        if curve is None:
            if had:
                self.end_song()
            return
        if not had:
            self._general = (self.enabled, self.preamp, list(self.gains), self.preset, self.origin)
        self.song_id = song_id
        self.enabled, self.preamp, self.gains = True, _clamp(curve["preamp"]), [_clamp(g) for g in curve["gains"]]
        self.preset = curve.get("name") or self._matching_preset()
        self.origin = curve.get("name") or None
        self.changed.emit()

    def end_song(self) -> None:
        """Back to the general equalizer (the song ended, or the person asked for it)."""
        if self.song_id is None:
            return
        self.song_id = None
        if self._general is not None:
            self.enabled, self.preamp, gains, self.preset, self.origin = self._general
            self.gains = list(gains)
        self._general = None
        self.changed.emit()

    def clear_song(self) -> None:
        """The person chose the general equalizer for the song that is playing: its own curve is dropped."""
        song = self.song_id
        if song is None:
            return
        self.end_song()
        self.song_cleared.emit(song)
