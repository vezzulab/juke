import re
import unittest

from . import helpers  # noqa: F401  (sets XDG env first)

from PySide6.QtWidgets import QApplication

from juke import manual
from juke.i18n import translator

app = QApplication.instance() or QApplication([])


class ManualContentTests(unittest.TestCase):
    def test_both_languages_have_the_same_book_for_each_system(self):
        for platform in ("linux", "android"):
            en, es = manual.load("en", platform), manual.load("es", platform)
            self.assertEqual(len(en), len(es), platform)                                    # same chapters
            self.assertEqual([len(c.sections) for c in en], [len(c.sections) for c in es], platform)   # same sections
            for chapter in en + es:
                self.assertTrue(chapter.title and chapter.body.strip(), platform)

    def test_each_system_gets_only_its_own_parts(self):
        linux, android = manual.load("en", "linux"), manual.load("en", "android")
        self.assertGreater(len(linux), len(android))                                       # folders, phones and shortcuts are Linux
        self.assertIn("Keyboard shortcuts", [c.title for c in linux])
        self.assertNotIn("Keyboard shortcuts", [c.title for c in android])
        for chapters in (linux, android):
            for chapter in chapters:
                self.assertNotIn("<!--", chapter.body, chapter.title)                       # no tag is left over
        self.assertFalse(any("img/linux" in c.body for c in android))                       # the phone never needs the PC's pictures
        self.assertFalse(any("img/android" in c.body for c in linux))

    def test_every_picture_of_the_book_exists(self):
        for code in manual.LANGUAGES:
            text = (manual.MANUAL_DIR / f"manual-{code}.md").read_text(encoding="utf-8")
            for path in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
                self.assertTrue((manual.MANUAL_DIR / path).is_file(), f"{code}: {path}")

    def test_what_the_book_says_about_the_keyboard_is_what_juke_does(self):
        """The shortcuts table of the manual and the real shortcuts of the window must not drift apart."""
        import inspect
        from juke.gui import main_window

        source = inspect.getsource(main_window)
        for chapter in manual.load("en", "linux"):
            if chapter.title == "Keyboard shortcuts":
                for keys in ("Ctrl` + `F", "Ctrl` + `N", "Ctrl` + `E", "Ctrl` + `L", "Ctrl` + `T", "Ctrl` + `,", "Ctrl` + `Q", "F1"):
                    token = keys.replace("` + `", "+").replace("Ctrl", "Ctrl")
                    self.assertIn(f'"{token}"', source, token)


class ManualWindowTests(unittest.TestCase):
    def test_the_manual_opens_with_its_index_and_follows_the_language(self):
        from juke.gui.manual_dialog import ManualDialog

        translator.set_language("en")
        dialog = ManualDialog()
        chapters = manual.load("en", "linux")
        self.assertEqual(dialog.index.topLevelItemCount(), len(chapters))
        self.assertTrue(dialog.chapter_title.text().startswith("1."))
        dialog.next.click()
        self.assertEqual(dialog._current, 1)
        translator.set_language("es")                                                      # the language of the app changes it
        self.assertEqual(dialog.index.topLevelItem(0).text(0).split(".")[0], "1")
        self.assertIn("Bienvenido", dialog.chapter_title.text() + dialog.index.topLevelItem(0).text(0))
        self.assertEqual(dialog._current, 1)                                               # ...and it stays on the same page
        dialog.search.setText("crossfade")                                                 # searching narrows the index
        shown = [i for i in range(dialog.index.topLevelItemCount()) if not dialog.index.topLevelItem(i).isHidden()]
        self.assertTrue(0 < len(shown) < dialog.index.topLevelItemCount())
        translator.set_language("en")


if __name__ == "__main__":
    unittest.main()


class AndroidManualTests(unittest.TestCase):
    """Juke for Android reads the same book. It is Kotlin, so what can be checked here is that it is wired to the same text."""

    ANDROID = (manual.MANUAL_DIR.parent.parent.parent / "android" / "app")

    def test_the_apk_takes_the_text_and_its_own_pictures_from_the_shared_book(self):
        gradle = (self.ANDROID / "build.gradle.kts").read_text(encoding="utf-8")
        self.assertIn("juke/assets/manual", gradle)
        self.assertIn('include("*.md")', gradle)
        self.assertIn('include("img/android/**")', gradle)                              # the PC's screenshots stay out of the APK
        self.assertIn('dependsOn(copyManual)', gradle)

    def test_the_kotlin_reader_filters_the_same_way_as_the_python_one(self):
        kotlin = (self.ANDROID / "src/main/java/io/github/vezzulab/juke/data/Manual.kt").read_text(encoding="utf-8")
        self.assertIn('"<!--(linux|android)-->(.*?)<!--/\\\\1-->"', kotlin)
        self.assertIn('manual-$code.md', kotlin)

    def test_the_app_can_open_it_and_says_so_in_both_languages(self):
        settings = (self.ANDROID / "src/main/java/io/github/vezzulab/juke/ui/SettingsScreen.kt").read_text(encoding="utf-8")
        self.assertIn("ManualScreen", settings)
        for values in ("values", "values-es"):
            strings = (self.ANDROID / f"src/main/res/{values}/strings.xml").read_text(encoding="utf-8")
            for name in ("manual_title", "manual_open", "manual_contents", "manual_previous", "manual_next"):
                self.assertIn(f'name="{name}"', strings, f"{values}: {name}")

    def test_the_phone_pictures_exist(self):
        text = (manual.MANUAL_DIR / "manual-en.md").read_text(encoding="utf-8")
        for path in re.findall(r"!\[[^\]]*\]\((img/android/[^)]+)\)", text):
            self.assertTrue((manual.MANUAL_DIR / path).is_file(), path)
