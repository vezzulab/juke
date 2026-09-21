import unittest
from pathlib import Path

from . import helpers  # noqa: F401  (sets XDG env first)

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

import juke.gui.meta_dialog as md
from juke.db.indexer import cover_path, extract_cover, prepare_cover, read_tags, write_cover
from juke.i18n import translator

from .test_gui import make_window


def picture(path: Path, color: str = "#c0392b", size: int = 300) -> Path:
    image = QImage(size, size, QImage.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")
    return path


class MetadataDialogTests(unittest.TestCase):
    def setUp(self):
        translator.set_language("en")
        self.window, self.cfg, self.db, self.engine, self.eq = make_window(f"meta-{self._testMethodName}", n=6)
        self.tracks = [t for t in self.db.tracks_by_ids(self.db.query_ids()) if t.is_local]
        self.folder = Path(self.tracks[0].location).parent

    def tearDown(self):
        self.window.close()

    def test_a_picked_image_becomes_the_cover_and_goes_into_the_file(self):
        track = self.tracks[0]
        dialog = md.MetadataDialog(track, self.db)
        self.assertTrue(dialog.set_cover_from_file(str(picture(self.folder / "front.png"))))
        dialog._save()
        again = self.db.get_track(track.id)
        self.assertTrue(again.cover_key)
        self.assertTrue(cover_path(again.cover_key).exists())
        self.assertTrue(extract_cover(track.location))          # embedded in the song itself

    def test_a_cover_can_be_taken_out_again(self):
        track = self.tracks[1]
        dialog = md.MetadataDialog(track, self.db)
        dialog.set_cover_from_file(str(picture(self.folder / "back.png", "#2980b9")))
        dialog._save()
        dialog = md.MetadataDialog(self.db.get_track(track.id), self.db)
        dialog._remove_cover()
        dialog._save()
        self.assertEqual(self.db.get_track(track.id).cover_key, "")

    def test_editing_a_group_only_changes_what_was_typed(self):
        ids = [t.id for t in self.tracks[:3]]
        before = {t.id: (t.title, t.album) for t in self.db.tracks_by_ids(ids)}
        dialog = md.MetadataDialog(self.db.tracks_by_ids(ids), self.db)
        self.assertFalse(dialog.title.isEnabled())               # one title for many songs makes no sense
        dialog.genre.setText("Road")
        dialog.genre.textEdited.emit("Road")
        dialog.set_cover_from_file(str(picture(self.folder / "group.png", "#27ae60")))
        dialog._save()
        for track in self.db.tracks_by_ids(ids):
            self.assertEqual(track.genre, "Road")
            self.assertEqual((track.title, track.album), before[track.id])   # untouched
            self.assertTrue(track.cover_key)
            self.assertEqual(read_tags(track.location)["genre"], "Road")

    def test_the_menu_now_allows_editing_several_songs(self):
        table = self.window.table
        table.selectAll()
        seen = []
        table.edit_requested.connect(seen.append)
        table.edit_requested.emit(table.selected_ids())
        self.assertGreater(len(seen[0]), 1)

    def test_something_that_is_not_an_image_is_refused(self):
        dialog = md.MetadataDialog(self.tracks[0], self.db)
        shown = []
        original, md.notice = md.notice, lambda *a, **k: shown.append(a)
        try:
            bogus = self.folder / "notes.png"
            bogus.write_bytes(b"not a picture")
            self.assertFalse(dialog.set_cover_from_file(str(bogus)))
        finally:
            md.notice = original
        self.assertTrue(shown)


if __name__ == "__main__":
    unittest.main()
