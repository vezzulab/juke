import re
import unittest
from pathlib import Path

from . import helpers  # noqa: F401  (sets XDG env first)

from juke.audio.equalizer import BUILTIN_PRESETS, MAX_DB, MIN_DB, SETUPS, headroom

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




class SetupTests(unittest.TestCase):
    def test_android_has_the_same_setups(self):
        source = ANDROID.read_text()
        block = source[source.index("val SETUPS"):source.index("fun headroom")]
        android = {n: tuple(float(x) for x in v.split(",")) for n, v in re.findall(r'"([^"]+)" to listOf\(([^)]*)\)', block)}
        self.assertEqual({k: tuple(map(float, v)) for k, v in SETUPS.items()}, android)

    def test_a_setup_is_added_to_the_curve_and_never_replaces_it(self):
        from juke.audio.equalizer import Equalizer
        from juke.config import Config

        eq = Equalizer(Config(Path(helpers.ROOT) / "eq-setup.json"))
        eq.set_band(0, 5)
        eq.set_setup("Small Room")
        self.assertEqual(eq.gains[0], 5)                                   # the curve is untouched
        self.assertEqual(eq.effective_gains()[0], 5 + SETUPS["Small Room"][0])
        self.assertLessEqual(max(g + eq.effective_preamp() for g in [0.0]), 0.0)
        eq.set_setup(None)
        self.assertEqual(eq.effective_gains(), eq.gains)


class AdvancedTests(unittest.TestCase):
    def make(self, name):
        from juke.audio.equalizer import Equalizer
        from juke.config import Config
        return Equalizer(Config(Path(helpers.ROOT) / name))

    def test_echo_takes_down_the_low_mids_and_leaves_the_curve_alone(self):
        eq = self.make("eq-adv1.json")
        eq.set_advanced("echo", 100)
        self.assertTrue(eq.enabled)
        self.assertEqual(eq.gains, [0.0] * 10)
        self.assertLess(eq.effective_gains()[2], -4)
        self.assertEqual(eq.effective_gains()[9], 0)
        eq.reset_advanced()
        self.assertEqual(eq.effective_gains(), [0.0] * 10)

    def test_the_setting_amount_scales_the_setup_and_it_is_remembered(self):
        eq = self.make("eq-adv2.json")
        eq.set_setup("Small Room")
        full = eq.effective_gains()[2]
        eq.set_advanced("room", 50)
        self.assertAlmostEqual(eq.effective_gains()[2], full / 2)
        from juke.audio.equalizer import Equalizer
        again = Equalizer(eq._config)
        self.assertEqual(again.advanced["room"], 50)
        self.assertEqual(again.setup, "Small Room")

    def test_shrill_voice_takes_down_the_harsh_mids_only(self):
        eq = self.make("eq-adv4.json")
        eq.set_advanced("shrill", 100)
        gains = eq.effective_gains()
        self.assertLess(gains[5], -3)
        self.assertLess(gains[6], -4)
        self.assertEqual(gains[0], 0)
        self.assertEqual(gains[9], 0)

    def test_advanced_boosts_never_clip(self):
        eq = self.make("eq-adv3.json")
        eq.set_advanced("clarity", 100)
        top = max(g + eq.effective_preamp() for g in eq.effective_gains())
        self.assertLessEqual(top, 1e-9)


class UpdatePresetTests(unittest.TestCase):
    def test_a_song_curve_can_be_kept_in_the_preset_it_came_from(self):
        from juke.audio.equalizer import Equalizer
        from juke.config import Config

        eq = Equalizer(Config(Path(helpers.ROOT) / "eq-upd.json"))
        eq.set_band(0, 3)
        eq.save_custom("Mine")
        eq.set_band(1, 7)                                              # an edit, which is not in the preset yet
        self.assertEqual(eq.custom["Mine"]["gains"][1], 0)
        self.assertTrue(eq.update_preset())
        self.assertEqual(eq.custom["Mine"]["gains"][1], 7)
        eq.load_preset("Rock")
        self.assertFalse(eq.update_preset())                           # a built-in preset never changes


class EngineLevelTests(unittest.TestCase):
    """libVLC's equalizer is 12 dB down at preamp 0, so Juke's "Level +0.0" must reach it as 12: a flat curve is the
    song exactly as it is. (Measured on a real output: flat was 12.0 dB quieter than no equalizer before this.)"""

    def make_engine(self):
        from juke.audio.engine import AudioEngine
        from juke.audio.equalizer import Equalizer
        from juke.config import Config

        sent = {}

        class Native:
            def set_preamp(self, db):
                sent["preamp"] = db

            def set_amp_at_index(self, gain, band):
                sent.setdefault("gains", {})[band] = gain

        class Vlc:
            AudioEqualizer = Native

        class Player:
            def set_equalizer(self, eq):
                sent["applied"] = eq

        engine = AudioEngine()
        engine._vlc, engine._player = Vlc(), Player()
        eq = Equalizer(Config(Path(helpers.ROOT) / "eq-level.json"))
        engine._equalizer = eq
        return engine, eq, sent

    def test_a_flat_equalizer_reaches_libvlc_at_its_unity_level(self):
        from juke.audio.engine import VLC_UNITY_PREAMP

        engine, eq, sent = self.make_engine()
        eq.enabled, eq.preamp, eq.gains = True, 0.0, [0.0] * 10
        engine._apply_equalizer()
        self.assertEqual(VLC_UNITY_PREAMP, 12.0)
        self.assertEqual(sent["preamp"], 12.0)
        self.assertEqual(sent["gains"][0], 0.0)

    def test_the_level_slider_moves_it_from_there_and_stays_in_libvlcs_range(self):
        engine, eq, sent = self.make_engine()
        eq.enabled = True
        for level, expected in ((-5.0, 7.0), (3.0, 15.0), (20.0, 20.0), (-20.0, -8.0)):    # (libVLC accepts -20..+20)
            eq.preamp = level
            engine._apply_equalizer()
            self.assertEqual(sent["preamp"], expected, level)

    def test_a_built_in_preset_keeps_its_headroom_on_top_of_that(self):
        engine, eq, sent = self.make_engine()
        eq.enabled = True
        eq.load_preset("Dembow")
        engine._apply_equalizer()
        self.assertEqual(sent["preamp"], 12.0 + headroom(BUILTIN_PRESETS["Dembow"]))


if __name__ == "__main__":
    unittest.main()
