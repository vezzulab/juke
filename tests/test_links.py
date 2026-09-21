import unittest

from . import helpers  # noqa: F401  (sets XDG env first)

from juke.links import desktop_environment


class LinkEnvironmentTests(unittest.TestCase):
    def test_what_the_appimage_added_is_taken_out(self):
        inside = "/tmp/.mount_JukeXYZ"
        env = {
            "APPDIR": inside, "PYTHONHOME": inside + "/usr/python", "PYTHONPATH": inside + "/usr/python/site-packages",
            "VLC_PLUGIN_PATH": inside + "/usr/lib/vlc/plugins",
            "LD_LIBRARY_PATH": f"{inside}/usr/lib:{inside}/usr/python/lib:/opt/mine/lib",
            "PATH": f"{inside}/usr/python/bin:/usr/bin:/bin",
            "XDG_DATA_DIRS": f"{inside}/usr/share:/usr/share",
            "HOME": "/home/x", "DISPLAY": ":0",
        }
        clean = desktop_environment(env)
        self.assertEqual(clean["LD_LIBRARY_PATH"], "/opt/mine/lib")           # the user's own entries stay
        self.assertEqual(clean["PATH"], "/usr/bin:/bin")
        self.assertEqual(clean["XDG_DATA_DIRS"], "/usr/share")
        for gone in ("APPDIR", "PYTHONHOME", "PYTHONPATH", "VLC_PLUGIN_PATH"):
            self.assertNotIn(gone, clean)
        self.assertEqual((clean["HOME"], clean["DISPLAY"]), ("/home/x", ":0"))

    def test_a_list_that_only_held_appimage_entries_disappears(self):
        inside = "/tmp/.mount_JukeXYZ"
        clean = desktop_environment({"APPDIR": inside, "LD_LIBRARY_PATH": inside + "/usr/lib", "PATH": "/usr/bin"})
        self.assertNotIn("LD_LIBRARY_PATH", clean)

    def test_outside_an_appimage_nothing_changes(self):
        env = {"PATH": "/usr/bin", "LD_LIBRARY_PATH": "/opt/x", "PYTHONHOME": "/somewhere"}
        self.assertEqual(desktop_environment(env), env)


if __name__ == "__main__":
    unittest.main()
