import sys
import types
import unittest
from unittest import mock

from . import helpers  # noqa: F401  (sets XDG env, and keeps tests off the desktop's bus)

from PySide6.QtWidgets import QApplication

from juke import config, integration, macmedia, power
from juke.devices import mtp

app = QApplication.instance() or QApplication([])


class FakeCommand:
    def __init__(self):
        self.handlers, self.enabled = [], False

    def setEnabled_(self, value):
        self.enabled = value

    def addTargetWithHandler_(self, handler):
        self.handlers.append(handler)
        return handler

    def removeTarget_(self, target):
        self.handlers.remove(target)


class FakeCenter:
    def __init__(self):
        self.info, self.state = "unset", None
        self.commands = {name: FakeCommand() for name in ("play", "pause", "togglePlayPause", "stop", "nextTrack", "previousTrack")}

    def playCommand(self): return self.commands["play"]
    def pauseCommand(self): return self.commands["pause"]
    def togglePlayPauseCommand(self): return self.commands["togglePlayPause"]
    def stopCommand(self): return self.commands["stop"]
    def nextTrackCommand(self): return self.commands["nextTrack"]
    def previousTrackCommand(self): return self.commands["previousTrack"]
    def setNowPlayingInfo_(self, info): self.info = info
    def setPlaybackState_(self, state): self.state = state


def fake_media_player(remote, now):
    module = types.ModuleType("MediaPlayer")
    module.MPRemoteCommandCenter = types.SimpleNamespace(sharedCommandCenter=lambda: remote)
    module.MPNowPlayingInfoCenter = types.SimpleNamespace(defaultCenter=lambda: now)
    module.MPRemoteCommandHandlerStatusSuccess = 0
    for name in ("Title", "Artist", "AlbumTitle", "PlaybackDuration"):
        setattr(module, f"MPMediaItem{'Property' + name}", f"item:{name}")
    module.MPNowPlayingInfoPropertyPlaybackRate = "rate"
    module.MPNowPlayingPlaybackStatePlaying, module.MPNowPlayingPlaybackStatePaused, module.MPNowPlayingPlaybackStateStopped = 1, 2, 3
    return module


class MacMediaTests(unittest.TestCase):
    """The system's media centre is faked: what matters is that the keys reach the window and the display gets the song."""

    def setUp(self):
        self.remote = self.now = FakeCenter()
        patch = mock.patch.dict(sys.modules, {"MediaPlayer": fake_media_player(self.remote, self.now)})
        patch.start()
        self.addCleanup(patch.stop)
        self.controls = macmedia.Controls()
        self.assertTrue(self.controls.register())

    def press(self, command):
        self.assertEqual(self.remote.commands[command].handlers[0](None), 0)       # the system is told it worked
        app.processEvents()

    def test_every_key_reaches_the_window(self):
        heard = []
        for name in ("play", "pause", "play_pause", "stop", "next", "previous"):
            getattr(self.controls, name).connect(lambda n=name: heard.append(n))
        for command in ("play", "pause", "togglePlayPause", "stop", "nextTrack", "previousTrack"):
            self.press(command)
        self.assertEqual(heard, ["play", "pause", "play_pause", "stop", "next", "previous"])
        self.assertTrue(all(c.enabled for c in self.remote.commands.values()))

    def test_the_display_shows_what_is_playing(self):
        self.controls.update(status="playing", title="Song", artist="Band", album="Record", length_us=3_000_000)
        self.controls._flush.timeout.emit()
        self.assertEqual(self.now.info["item:Title"], "Song")
        self.assertEqual(self.now.info["item:Artist"], "Band")
        self.assertEqual(self.now.info["item:PlaybackDuration"], 3.0)
        self.assertEqual((self.now.info["rate"], self.now.state), (1.0, 1))
        self.controls.update(status="paused")
        self.controls._flush.timeout.emit()
        self.assertEqual((self.now.info["rate"], self.now.state), (0.0, 2))

    def test_stopped_with_nothing_clears_the_display(self):
        self.controls.update(status="playing", title="Song")
        self.controls._flush.timeout.emit()
        self.controls.update(status="stopped", title="")
        self.controls._flush.timeout.emit()
        self.assertIsNone(self.now.info)
        self.assertEqual(self.now.state, 3)

    def test_unregistering_takes_the_keys_back(self):
        self.controls.unregister()
        self.assertTrue(all(not c.handlers for c in self.remote.commands.values()))


class MacPartsTests(unittest.TestCase):
    def test_battery_is_read_from_pmset(self):
        batt = "Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t80%; discharging; 5:10 remaining present: true\n"
        mains = "Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t80%; charging; 1:10 remaining present: true\n"
        for text, expected in ((batt, True), (mains, False)):
            with mock.patch.object(power, "IS_MAC", True), \
                    mock.patch.object(power.subprocess, "run", return_value=types.SimpleNamespace(stdout=text)):
                self.assertIs(power.on_battery(), expected)
        with mock.patch.object(power, "IS_MAC", True), mock.patch.object(power.subprocess, "run", side_effect=OSError):
            self.assertFalse(power.on_battery())                                             # a desktop Mac: mains power

    def test_there_is_no_menu_entry_or_phone_support_off_linux(self):
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertFalse(integration.supported())
            self.assertFalse(mtp.available())
        with mock.patch.object(sys, "platform", "linux"):
            self.assertTrue(integration.supported())

    def test_the_library_lives_where_a_mac_keeps_it(self):
        import os

        with mock.patch.dict(os.environ, clear=False):
            for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
                os.environ.pop(name, None)
            home = config.Path.home()
            self.assertEqual(config.locations(True), (home / "Library/Application Support/juke", home / "Library/Application Support/juke",
                                                      home / "Library/Caches/juke"))
            self.assertEqual(config.locations(False), (home / ".config/juke", home / ".local/share/juke", home / ".cache/juke"))
            os.environ["XDG_DATA_HOME"] = "/somewhere"
            self.assertEqual(config.locations(True)[1], config.Path("/somewhere/juke"))

    def test_the_icon_has_the_margin_macos_icons_have(self):
        from juke.gui import icons

        image = icons.mac_pixmap(1024).toImage()
        self.assertEqual(image.pixelColor(2, 2).alpha(), 0)                                  # the corners of the canvas are empty
        self.assertEqual(image.pixelColor(512, 512).alpha(), 255)                            # the artwork is in the middle
        margin = next(x for x in range(512) if image.pixelColor(x, 512).alpha() > 0)
        self.assertAlmostEqual(margin / 1024, (1 - icons.MAC_ARTWORK) / 2, delta=0.01)       # artwork 824 of 1024, like every other icon


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(sys.platform == "darwin", "the disk image tools are the Mac's")
class MacUpdateTests(unittest.TestCase):
    """An update on a Mac: the disk image is opened, the new app copied beside the old one and checked, and it takes the
    old one's place when Juke has closed."""

    def make_app(self, folder, name, label):
        import plistlib
        import subprocess
        from pathlib import Path

        app = Path(folder) / name
        (app / "Contents" / "MacOS").mkdir(parents=True)
        (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Juke", "CFBundleIdentifier": "test.juke", "CFBundleName": "Juke"}))
        (app / "Contents" / "MacOS" / "Juke").write_text("#!/bin/sh\necho " + label + "\n")
        (app / "Contents" / "MacOS" / "Juke").chmod(0o755)
        subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(app)], check=True, capture_output=True)
        return app

    def make_dmg(self, folder, label, sign=True):
        import shutil
        import subprocess
        from pathlib import Path

        stage = Path(folder) / "stage"
        stage.mkdir()
        app = self.make_app(stage, "Juke.app", label)
        if not sign:
            (app / "Contents" / "MacOS" / "Juke").write_text("tampered after signing\n")
        dmg = Path(folder) / "Juke.dmg"
        subprocess.run(["hdiutil", "create", "-quiet", "-volname", "Juke", "-srcfolder", str(stage), "-format", "UDZO", str(dmg)], check=True)
        shutil.rmtree(stage)
        return dmg

    def test_the_mac_asset_is_the_disk_image(self):
        from juke.updater import release_from_json

        payload = {"tag_name": "v9.0.0", "html_url": "u", "assets": [
            {"name": "Juke-x86_64.AppImage", "browser_download_url": "linux", "size": 1},
            {"name": "Juke-macos-arm64.dmg", "browser_download_url": "mac", "size": 2, "digest": "sha256:ABC"}]}
        self.assertEqual(release_from_json(payload, mac=True).asset_url, "mac")
        self.assertEqual(release_from_json(payload, mac=True).asset_sha256, "abc")
        self.assertEqual(release_from_json(payload).asset_url, "linux")

    def test_a_rebuilt_mac_release_is_told_by_its_build_id(self):
        from juke.updater import is_update, release_from_json

        payload = {"tag_name": "v%s", "html_url": "u", "body": "News\n<!-- juke-build:mac=222 -->",
                   "assets": [{"name": "Juke-macos-arm64.dmg", "browser_download_url": "mac", "size": 2}]}
        from juke import __version__

        release = release_from_json({**payload, "tag_name": "v" + __version__}, mac=True)
        self.assertEqual((release.asset_build, release.notes), ("222", "News"))
        release.installed_build = "111"
        self.assertTrue(release.is_rebuild and is_update(release))
        release.installed_build = "222"
        self.assertFalse(is_update(release))
        release.installed_build = ""                       # from source, or a build that did not say
        self.assertFalse(is_update(release))

    def test_stage_then_swap_replaces_the_app_when_the_old_one_has_quit(self):
        import subprocess
        import tempfile
        import time
        from pathlib import Path

        from juke import updater

        with tempfile.TemporaryDirectory() as folder:
            apps = Path(folder, "Applications")
            apps.mkdir()
            old = self.make_app(apps, "Juke.app", "old")
            dmg = self.make_dmg(Path(tempfile.mkdtemp(dir=folder)), "new")
            staged = updater.stage_mac_app(dmg, old)
            self.assertFalse(dmg.exists())                                   # the download is not left behind
            self.assertEqual(subprocess.run([str(staged / "Contents/MacOS/Juke")], capture_output=True, text=True).stdout.strip(), "new")
            self.assertEqual(subprocess.run([str(old / "Contents/MacOS/Juke")], capture_output=True, text=True).stdout.strip(), "old")
            quit_soon = subprocess.Popen(["/bin/sleep", "1"])                # "Juke" is still running for a second
            swap = updater.swap_app_after_exit(staged, old, open_after=False, pid=quit_soon.pid)
            time.sleep(0.4)
            self.assertEqual(subprocess.run([str(old / "Contents/MacOS/Juke")], capture_output=True, text=True).stdout.strip(), "old")   # not before it quits
            quit_soon.wait()
            swap.wait(timeout=20)
            self.assertEqual(subprocess.run([str(old / "Contents/MacOS/Juke")], capture_output=True, text=True).stdout.strip(), "new")
            self.assertEqual(sorted(p.name for p in apps.iterdir()), ["Juke.app"])    # no staged copy, no backup left

    def test_a_damaged_app_is_refused_and_nothing_is_left(self):
        import tempfile
        from pathlib import Path

        from juke import updater

        with tempfile.TemporaryDirectory() as folder:
            apps = Path(folder, "Applications")
            apps.mkdir()
            old = self.make_app(apps, "Juke.app", "old")
            dmg = self.make_dmg(Path(tempfile.mkdtemp(dir=folder)), "new", sign=False)
            with self.assertRaises(updater.UpdateError):
                updater.stage_mac_app(dmg, old)
            self.assertEqual(sorted(p.name for p in apps.iterdir()), ["Juke.app"])
