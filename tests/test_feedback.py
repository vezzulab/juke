import logging
import unittest
from pathlib import Path

from . import helpers  # noqa: F401  (sets XDG env first)

from PySide6.QtCore import QUrl

from juke import applog
from juke.gui import feedback_dialog as fd
from juke.i18n import translator

from .test_gui import make_window


class RedactionTests(unittest.TestCase):
    def test_private_details_are_hidden(self):
        home = str(Path.home())
        text = (f"opened {home}/Music/x.mp3\n"
                "GET http://me:hunter2@192.168.1.5:4040/rest/ping?u=luis&t=abc123&s=salt&c=juke\n"
                "server 192.168.1.5:4040 password swordfish")
        out = applog.redact(text, secrets=["swordfish", "192.168.1.5:4040", "luis"])
        for private in (home, "hunter2", "abc123", "swordfish", "192.168.1.5", "luis"):
            self.assertNotIn(private, out)
        self.assertIn("~/Music/x.mp3", out)
        self.assertIn("c=juke", out)                                  # harmless parts stay readable


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        translator.set_language("en")
        self.window, self.cfg, self.db, self.engine, self.eq = make_window("feedback", n=3)

    def tearDown(self):
        self.window.close()

    def test_the_log_is_written_and_shows_up_redacted(self):
        applog.setup()
        logging.getLogger("juke.test").warning("could not open %s with password=%s", Path.home() / "Music", "hunter22")
        dialog = fd.LogDialog(self.cfg)
        shown = dialog.text.toPlainText()
        self.assertIn("could not open", shown)
        self.assertNotIn(str(Path.home()), shown)

    def test_the_form_needs_a_message_and_builds_a_github_issue(self):
        self.cfg.set("airsonic", {"enabled": True, "url": "http://192.168.9.9:4040", "username": "luisq", "password": "swordfish", "auth": "auto"})
        dialog = fd.FeedbackDialog(self.cfg, ["Library: 3 local songs"])
        self.assertFalse(dialog.send.isEnabled())                     # nothing to send yet
        dialog.message.setPlainText("It stops after two songs\nseen on my server 192.168.9.9:4040")
        self.assertTrue(dialog.send.isEnabled())
        report = dialog.report(True)
        self.assertIn("Library: 3 local songs", report)
        self.assertNotIn("192.168.9.9", report)
        url = dialog._issue_url(dialog.report(False))
        self.assertTrue(url.toString().startswith("https://github.com/vezzulab/juke/issues/new?"))
        self.assertIn("It stops after two songs", QUrl.fromPercentEncoding(url.query().encode()))
        dialog.include.setChecked(False)
        self.assertNotIn("Juke ", dialog.report(True))                # details are optional


if __name__ == "__main__":
    unittest.main()
