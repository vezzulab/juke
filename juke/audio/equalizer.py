"""10-band graphic equalizer state, built-in and user presets.

The bands are the fixed ones libVLC exposes (``libvlc_audio_equalizer_get_band_frequency``);
gains and preamp are in dB within libVLC's ±20 dB range.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..config import Config

BANDS_HZ = (60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000)
BAND_LABELS = ("60", "170", "310", "600", "1K", "3K", "6K", "12K", "14K", "16K")
MIN_DB = -20.0
MAX_DB = 20.0

# name -> gains for BANDS_HZ (dB). Preamp is 0 for every built-in preset.
BUILTIN_PRESETS: dict[str, tuple[float, ...]] = {
    "Flat":        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    "Rock":        (4, 3, 2, -1, -2, -1, 2, 4, 5, 5),
    "Pop":         (-1, 3, 4, 5, 3, 0, -1, -2, -2, -2),
    "Jazz":        (3, 2, 1, 2, -2, -2, 0, 1, 2, 3),
    "Bass Boost":  (7, 6, 5, 3, 1, 0, 0, 0, 0, 0),
    "Vocal":       (-3, -3, -2, 1, 4, 4, 3, 1, 0, -1),
    "Classical":   (0, 0, 0, 0, 0, 0, -2, -3, -3, -4),
    "Electronic":  (5, 4, 1, 0, -2, 2, 1, 1, 4, 5),
    "Heavy Metal": (5, 4, 0, -3, -1, 2, 5, 6, 5, 4),
    "Techno":      (5, 4, 0, -4, -3, 0, 5, 6, 6, 5),
}


def _clamp(value: float) -> float:
    return max(MIN_DB, min(MAX_DB, float(value)))


class Equalizer(QObject):
    """Holds the current curve; ``changed`` fires after every edit."""

    changed = Signal()

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        state = config.get("equalizer")
        self.enabled: bool = bool(state["enabled"])
        self.preamp: float = _clamp(state["preamp"])
        self.gains: list[float] = [_clamp(g) for g in state["gains"]]
        self.preset: str | None = state["preset"]
        self.custom: dict[str, dict] = {
            name: {"preamp": _clamp(p["preamp"]), "gains": [_clamp(g) for g in p["gains"]]}
            for name, p in config.get("custom_presets", {}).items()
            if isinstance(p, dict) and len(p.get("gains", [])) == 10
        }

    # -- state ---------------------------------------------------------------
    def _persist(self) -> None:
        self._config.set("equalizer", {
            "enabled": self.enabled, "preamp": self.preamp,
            "gains": list(self.gains), "preset": self.preset,
        })
        self._config.set("custom_presets", self.custom)

    def _emit(self) -> None:
        self._persist()
        self.changed.emit()

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
        presets = {name: (0.0, tuple(map(float, gains))) for name, gains in BUILTIN_PRESETS.items()}
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
        self._emit()

    def save_custom(self, name: str) -> bool:
        """Store the current curve under ``name``; built-in names are protected."""
        name = name.strip()
        if not name or name in BUILTIN_PRESETS:
            return False
        self.custom[name] = {"preamp": self.preamp, "gains": list(self.gains)}
        self.preset = name
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
