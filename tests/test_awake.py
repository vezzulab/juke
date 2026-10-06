import unittest

from . import helpers  # noqa: F401  (sets XDG env, and keeps tests off the desktop's bus)

from PySide6.QtWidgets import QApplication

from juke import awake

app = QApplication.instance() or QApplication([])


class StayAwakeTests(unittest.TestCase):
    """The desktop is faked: what matters is when Juke asks, and that it never asks twice or forgets to let go."""

    def setUp(self):
        self.calls = []
        self.opened, self.closed = [], []
        self._call, self._connect, self._disconnect = awake._call, awake.QDBusConnection.connectToBus, awake.QDBusConnection.disconnectFromBus

        def fake_call(bus, service, path, interface, method, *args):
            self.calls.append((service, method))
            return "fd-held" if service == "org.freedesktop.login1" else 7

        awake._call = fake_call
        awake.QDBusConnection.connectToBus = staticmethod(lambda kind, name: self.opened.append(name) or object())
        awake.QDBusConnection.disconnectFromBus = staticmethod(lambda name: self.closed.append(name))

    def tearDown(self):
        awake._call, awake.QDBusConnection.connectToBus, awake.QDBusConnection.disconnectFromBus = self._call, self._connect, self._disconnect

    def test_it_asks_when_music_starts_and_lets_go_when_it_stops(self):
        stay = awake.StayAwake()
        stay.set(True)
        self.assertTrue(stay.active)
        self.assertEqual(stay.methods, ["PowerManagement", "ScreenSaver", "logind"])        # every standard way that is there
        self.assertEqual(len(self.opened), 1)
        stay.set(False)
        self.assertFalse(stay.active)
        self.assertEqual(self.closed, self.opened)                                          # the connection that asked is closed
        self.assertIsNone(stay._lock)                                                       # ...and so is the logind lock

    def test_playing_twice_does_not_pile_up_requests(self):
        stay = awake.StayAwake()
        stay.set(True)
        before = len(self.calls)
        stay.set(True)                                                                      # (a new song starts: still playing)
        self.assertEqual(len(self.calls), before)
        stay.set(False)
        stay.set(False)                                                                     # (stopped twice)
        self.assertEqual(len(self.closed), 1)

    def test_each_play_gets_a_fresh_request(self):
        stay = awake.StayAwake()
        for _ in range(3):
            stay.set(True)
            stay.set(False)
        self.assertEqual(len(self.opened), 3)
        self.assertEqual(len(set(self.opened)), 3)                                          # a new connection every time: nothing is reused
        self.assertEqual(self.closed, self.opened)

    def test_turned_off_in_settings_it_never_asks(self):
        stay = awake.StayAwake()
        stay.enabled = False
        stay.set(True)
        self.assertFalse(stay.active)
        self.assertEqual(self.calls, [])
        stay.enabled = True
        stay.set(True)
        stay.enabled = False                                                                # turned off while playing: it lets go
        stay.set(True)
        self.assertFalse(stay.active)
        self.assertEqual(self.closed, self.opened)

    def test_a_desktop_that_answers_nothing_is_not_an_error(self):
        awake._call = lambda *a, **k: None
        stay = awake.StayAwake()
        stay.set(True)
        self.assertEqual(stay.methods, [])                                                  # nothing to hold, and nothing breaks
        stay.set(False)
        self.assertFalse(stay.active)


class WindowKeepsAwakeTests(unittest.TestCase):
    def test_playing_asks_and_pausing_lets_go(self):
        from .test_gui import make_window, pump

        window, cfg, db, engine, eq = make_window("awake1", n=3)
        events = []
        window.awake.set = events.append                                                    # watch what the window tells it
        engine.state_changed.emit("playing")
        engine.state_changed.emit("paused")
        engine.state_changed.emit("playing")
        engine.state_changed.emit("stopped")
        self.assertEqual(events, [True, False, True, False])
        window.close()

    def test_the_setting_is_in_the_playback_tab_and_on_by_default(self):
        from juke.config import Config
        from juke.gui.settings_dialog import SettingsDialog
        from pathlib import Path

        cfg = Config(Path(helpers.ROOT) / "awake-settings.json")
        self.assertTrue(cfg.get("stay_awake"))
        dialog = SettingsDialog(cfg, False)
        self.assertTrue(dialog.stay_awake.isChecked())
        dialog.stay_awake.setChecked(False)
        dialog.apply_to(cfg)
        self.assertFalse(cfg.get("stay_awake"))


if __name__ == "__main__":
    unittest.main()
