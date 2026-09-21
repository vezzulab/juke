import re
import unittest
from pathlib import Path

from . import helpers  # noqa: F401  (sets XDG env first)

from juke.audio.equalizer import BUILTIN_PRESETS, MAX_DB, MIN_DB, headroom

ANDROID = Path(__file__).resolve().parent.parent / "android/app/src/main/java/io/github/vezzulab/juke/playback/EqualizerHub.kt"


def android_presets() -> dict[str, tuple[float, ...]]:
    """The preset table as written in the Android source."""
    source = ANDROID.read_text()
    block = source[source.index("val PRESETS"):source.index(".mapValues")]
    return {name: tuple(float(n) for n in numbers.split(","))
            for name, numbers in re.findall(r'"([^"]+)" to listOf\(([^)]*)\)', block)}


class PresetTests(unittest.TestCase):
    def test_the_caribbean_genres_are_there(self):
        for name in ("Dembow", "Reggaeton", "Salsa", "Merengue", "Bachata"):
            self.assertIn(name, BUILTIN_PRESETS)

    def test_every_preset_has_the_ten_bands_inside_the_range(self):
        for name, gains in BUILTIN_PRESETS.items():
            self.assertEqual(len(gains), 10, name)
            self.assertTrue(all(MIN_DB <= g <= MAX_DB for g in gains), name)

    def test_a_boost_can_never_clip(self):
        """Played at its own headroom, the loudest band of a preset never goes above 0 dB."""
        for name, gains in BUILTIN_PRESETS.items():
            self.assertLessEqual(max(g + headroom(gains) for g in gains), 1e-9, name)
            self.assertLessEqual(headroom(gains), 0.0, name)

    def test_flat_stays_flat_and_untouched(self):
        self.assertEqual(headroom(BUILTIN_PRESETS["Flat"]), 0.0)

    def test_curves_are_smooth(self):
        """A jagged curve sounds phasey, not better: neighbouring bands never jump by more than 3 dB."""
        for name, gains in BUILTIN_PRESETS.items():
            steps = [abs(b - a) for a, b in zip(gains, gains[1:])]
            self.assertLessEqual(max(steps), 3, f"{name}: {gains}")

    def test_what_each_genre_is_about(self):
        low = lambda n: sum(BUILTIN_PRESETS[n][:2])
        high = lambda n: sum(BUILTIN_PRESETS[n][6:])
        self.assertGreater(low("Dembow"), low("Salsa"))                 # dembow lives on the sub kick
        self.assertGreater(low("Reggaeton"), low("Bachata"))
        self.assertGreater(BUILTIN_PRESETS["Salsa"][5], BUILTIN_PRESETS["Salsa"][2])   # brass and timbales, not mud
        self.assertGreater(high("Merengue"), high("Reggaeton"))        # güira and tambora
        self.assertGreater(BUILTIN_PRESETS["Bachata"][5], BUILTIN_PRESETS["Bachata"][0])   # the requinto guitar

    def test_android_has_exactly_the_same_curves(self):
        self.assertEqual({k: tuple(map(float, v)) for k, v in BUILTIN_PRESETS.items()}, android_presets())

    def test_loading_a_preset_applies_its_headroom(self):
        from juke.audio.equalizer import Equalizer
        from juke.config import Config

        eq = Equalizer(Config(Path(helpers.ROOT) / "eq-settings.json"))
        eq.load_preset("Dembow")
        self.assertEqual(eq.preamp, headroom(BUILTIN_PRESETS["Dembow"]))
        self.assertEqual(eq.preset, "Dembow")
        eq.set_band(0, 0)                                               # touching a band makes it a custom curve...
        self.assertIsNone(eq.preset)
        eq.load_preset("Dembow")                                        # ...and the preset is recognised again
        self.assertEqual(eq.preset, "Dembow")


if __name__ == "__main__":
    unittest.main()
