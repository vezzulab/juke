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


class OpeningALinkTests(unittest.TestCase):
    """The click must open something, or say why it could not."""

    def setUp(self):
        import juke.links as links
        self.links = links
        self.saved = (links._via_portal, links._via_program)

    def tearDown(self):
        self.links._via_portal, self.links._via_program = self.saved

    def test_the_desktop_portal_is_tried_first_then_the_programs(self):
        calls = []
        self.links._via_portal = lambda t: calls.append("portal") or False
        self.links._via_program = lambda t: calls.append("program") or True
        self.assertTrue(self.links.open_url("https://ko-fi.com/S1K526XVUI"))
        self.assertEqual(calls, ["portal", "program"])

    def test_when_the_portal_works_nothing_else_is_launched(self):
        calls = []
        self.links._via_portal = lambda t: calls.append("portal") or True
        self.links._via_program = lambda t: calls.append("program") or True
        self.assertTrue(self.links.open_url("https://ko-fi.com/S1K526XVUI"))
        self.assertEqual(calls, ["portal"])

    def test_when_nothing_opens_the_address_is_copied_and_the_person_is_told(self):
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication([])
        told = []
        original = QMessageBox.information
        QMessageBox.information = lambda *a, **k: told.append(a[-1])
        try:
            self.links._via_portal = lambda t: False
            self.links._via_program = lambda t: False
            self.assertFalse(self.links.open_url("https://ko-fi.com/S1K526XVUI"))
        finally:
            QMessageBox.information = original
        self.assertEqual(QGuiApplication.clipboard().text(), "https://ko-fi.com/S1K526XVUI")
        self.assertTrue(told and "ko-fi.com" in told[0])


class StartDetachedShapeTests(unittest.TestCase):
    def test_both_return_shapes_of_startdetached_are_understood(self):
        """PySide6 builds differ: some return (started, pid), some only started. Either must count."""
        from juke.links import _started
        self.assertTrue(_started((True, 1234)))
        self.assertTrue(_started(True))
        self.assertFalse(_started((False, 0)))
        self.assertFalse(_started(False))


class KofiButtonTests(unittest.TestCase):
    def test_pressing_support_on_kofi_opens_the_kofi_page(self):
        from PySide6.QtWidgets import QApplication
        import juke.links as links
        from .test_gui import make_window, pump

        window, *_ = make_window("kofi-click", n=1)
        opened = []
        original = links.open_url
        links.open_url = lambda url: opened.append(url.toString() if hasattr(url, "toString") else str(url)) or True
        try:
            links.install_handlers(QApplication.instance())            # what main() does at start-up
            window.support_button.click()
            pump(100)
        finally:
            links.open_url = original
            window.close()
        self.assertEqual(opened, ["https://ko-fi.com/S1K526XVUI"])
