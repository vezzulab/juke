import json
import unittest
from pathlib import Path

from . import helpers  # noqa: F401  (sets XDG env first)

from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl, Qt
from PySide6.QtGui import QContextMenuEvent, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

import juke.gui.main_window as mw
from juke.db.database import SOURCE_LOCAL, Scope
from juke.gui.components.sidebar import COUNT_ROLE, MIME_FOLDER, MIME_TRACKS
from juke.i18n import translator

from .test_core import row, write_wav
from .test_gui import make_window, pump


def drag_through(sidebar, target, mime, actions=Qt.CopyAction, start_over=None):
    """Play a whole drag the way the window system does, through the event loop: it enters over
    ``start_over`` (any row, any heading), moves onto ``target`` and is dropped there.
    Returns (entered, over_target, dropped)."""
    view = sidebar.viewport()
    where = lambda item: sidebar.visualItemRect(item).center()
    start = where(start_over or sidebar._items[("all", None)])
    enter = QDragEnterEvent(start, actions, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(view, enter)
    move = QDragMoveEvent(where(target), actions, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(view, move)
    drop = QDropEvent(QPointF(where(target)), actions, mime, Qt.LeftButton, Qt.NoModifier)
    if move.isAccepted():
        QApplication.sendEvent(view, drop)         # a widget that ignored the move is never sent the drop
    return enter.isAccepted(), move.isAccepted(), drop.isAccepted()


def tracks_mime(ids):
    mime = QMimeData()
    mime.setData(MIME_TRACKS, json.dumps(ids).encode())
    return mime


class FoldersGuiTests(unittest.TestCase):
    def setUp(self):
        translator.set_language("en")
        self.window, self.cfg, self.db, self.engine, self.eq = make_window(f"folders-{self._testMethodName}", n=12)
        self.sidebar, self.store = self.window.sidebar, self.window.folders
        self.names = []
        self._orig = (mw.ask_text, mw.confirm)
        mw.ask_text = lambda *a, **k: self.names.pop(0) if self.names else None
        mw.confirm = lambda *a, **k: True

    def tearDown(self):
        mw.ask_text, mw.confirm = self._orig
        self.window.close()

    def wait_for(self, condition, seconds=8):
        import time
        end = time.monotonic() + seconds
        while time.monotonic() < end and not condition():
            pump(30)
        return condition()

    def real_ids(self, n):
        """Ids of n songs whose files really exist (a folder only takes files that are there)."""
        import tempfile
        folder = Path(tempfile.mkdtemp(prefix="juke-real-"))
        rows = []
        for i in range(n):
            path = folder / f"real{i}.wav"
            write_wav(path, 0.2)
            rows.append(row(900 + i, location=str(path)))
        self.db.upsert_many(rows)
        self.window.refresh_library()
        pump(100)
        return [t.id for t in self.db.tracks_by_ids(self.db.query_ids()) if t.location.startswith(str(folder))]

    def folder_rows(self):
        header = self.sidebar._headers["folders"]
        return [header.child(i).text(0) for i in range(header.childCount())]

    # ------------------------------------------------------------------------------------------
    def test_sidebar_order_and_what_no_longer_lives_there(self):
        sidebar = self.sidebar
        headers = [sidebar.topLevelItem(i).text(0) for i in range(sidebar.topLevelItemCount())]
        self.assertEqual(headers, ["LIBRARY", "SERVERS", "RADIO", "PLAYLISTS", "FOLDERS"])
        for gone in ("favorites", "recent", "queue"):
            self.assertNotIn((gone, None), sidebar._items)
        self.assertEqual(sidebar._headers["lists"].childCount(), 0)
        translator.set_language("es")
        pump(50)
        self.assertEqual(sidebar._headers["folders"].text(0), "CARPETAS")
        translator.set_language("en")
        pump(50)
        menu = self.window.menu_button.menu()
        titles = [a.text().split("\t")[0] for a in menu.actions() if a.menu()]
        self.assertEqual(titles, ["Show", "Find Duplicates"])
        shown = [a.text() for a in next(a for a in menu.actions() if a.text() == "Show").menu().actions()]
        self.assertEqual(shown, ["Favorites", "Recently Played", "Current Queue"])

    def test_create_rename_nest_sort_duplicate_and_delete(self):
        w = self.window
        self.names = ["Party", "Chill", "Slow", "2019"]
        w._new_folder(); w._new_folder(); w._new_folder()
        self.assertEqual(self.folder_rows(), ["Chill", "Party", "Slow"])
        party = next(f for f in self.store.tree() if f.name == "Party")
        w._new_folder(party.id)
        self.assertEqual(self.store.path_of(w._view[1]), "Party / 2019")
        self.assertIn("Party / 2019", w.subtitle_label.text())
        w._sort_folders(0, "name_desc")
        self.assertEqual(self.folder_rows(), ["Slow", "Party", "Chill"])
        self.names = ["10 Rock", "2 Pop"]
        w._new_folder(); w._new_folder()
        w._sort_folders(0, "number")
        self.assertEqual(self.folder_rows()[:2], ["2 Pop", "10 Rock"])
        w._sort_folders(0, "name")
        self.names = ["Fiesta"]
        w._rename_folder(party.id)
        self.assertIn("Fiesta", self.folder_rows())
        w._folder_action("duplicate", party.id)
        self.assertIn("Fiesta 2", self.folder_rows())
        w._delete_folder(party.id)
        self.assertNotIn("Fiesta", self.folder_rows())
        self.assertTrue(w._view[0] == "all" or (w._view[0] == "ufolder" and self.store.get(int(w._view[1])) is not None))   # never a folder that is gone

    def test_a_drag_is_accepted_wherever_it_enters_and_lands_on_the_right_row(self):
        """Regression: refusing the enter (because it happened to be over a heading) killed the whole drag."""
        w, db = self.window, self.db
        ids = self.real_ids(2)
        self.names = ["Merengue"]
        w._new_folder()
        folder = self.store.tree()[0]
        item = self.sidebar._items[("ufolder", folder.id)]
        for start_name in ("radio", "folders", "all", "self"):
            item = self.sidebar._items[("ufolder", folder.id)]                   # the rows are rebuilt after every drop
            start = item if start_name == "self" else self.sidebar._headers.get(start_name) or self.sidebar._items[("all", None)]
            entered, over, dropped = drag_through(self.sidebar, item, tracks_mime(ids[:2]), start_over=start)
            self.assertTrue(entered and over and dropped)                        # however it came in
        item = self.sidebar._items[("ufolder", folder.id)]
        self.assertEqual(item.data(0, COUNT_ROLE), 2)
        self.assertIn("Added 2 songs", w.statusBar().currentMessage())

    def test_songs_dragged_from_the_table_into_a_folder_and_a_playlist(self):
        w, db = self.window, self.db
        ids = self.real_ids(5)
        self.names = ["Merengue"]
        w._new_folder()
        folder = self.store.tree()[0]
        item = self.sidebar._items[("ufolder", folder.id)]
        model = w.table.track_model
        w._show_view("all", None)                                                           # the whole library in the table
        pump(100)
        mime = model.mimeData([model.index(0, 0), model.index(1, 0), model.index(1, 2)])
        self.assertEqual(len(json.loads(bytes(mime.data(MIME_TRACKS)).decode())), 2)     # one id per song, not per cell
        drag_through(self.sidebar, item, tracks_mime(ids[:3]))
        self.assertEqual(len(self.store.items(folder.id)), 3)
        w.sidebar.select("ufolder", folder.id)
        w._show_view("ufolder", folder.id)
        self.assertEqual(model.rowCount(), 3)
        drag_through(self.sidebar, item, tracks_mime(ids[:3]))                            # the same songs again: nothing new
        self.assertEqual(len(self.store.items(folder.id)), 3)
        pid = db.create_playlist("Mix")
        w.refresh_playlists()
        drag_through(self.sidebar, self.sidebar._items[("playlist", pid)], tracks_mime(ids[3:5]))
        self.assertEqual(db.playlist_track_ids(pid), ids[3:5])
        before = len(self.store.items(folder.id))
        entered, over, _ = drag_through(self.sidebar, self.sidebar._items[("all", None)], tracks_mime(ids[:2]))
        self.assertTrue(entered)
        self.assertFalse(over)                                                            # the library rows take nothing
        self.assertEqual(len(self.store.items(folder.id)), before)
        w.table.selectRow(0)
        w._remove_from_folder(w.table.selected_ids())
        self.assertEqual(len(self.store.items(folder.id)), 2)

    def test_files_and_folders_dragged_in_from_the_file_manager_need_no_import_step(self):
        w, db = self.window, self.db
        library = Path(helpers.ROOT) / "dropped-music"
        for rel in ("Rock/one.wav", "Rock/Live/two.wav", "loose.wav"):
            (library / rel).parent.mkdir(parents=True, exist_ok=True)
            write_wav(library / rel, 0.2)
        self.names = ["Mine"]
        w._new_folder()
        mine = self.store.tree()[0]
        item = self.sidebar._items[("ufolder", mine.id)]
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(library / "Rock")), QUrl.fromLocalFile(str(library / "loose.wav"))])
        # a file manager offers copy, move and link; whatever it proposes, Juke must answer "copy"
        view = self.sidebar.viewport()
        pos = self.sidebar.visualItemRect(item).center()
        move = QDragMoveEvent(pos, Qt.CopyAction | Qt.MoveAction | Qt.LinkAction, mime, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(view, QDragEnterEvent(pos, Qt.CopyAction | Qt.MoveAction | Qt.LinkAction, mime, Qt.LeftButton, Qt.NoModifier))
        QApplication.sendEvent(view, move)
        self.assertEqual(move.dropAction(), Qt.CopyAction)                                 # never "move": that would delete the originals
        drop = QDropEvent(QPointF(pos), Qt.CopyAction | Qt.MoveAction | Qt.LinkAction, mime, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(view, drop)
        self.assertEqual(drop.dropAction(), Qt.CopyAction)
        by_name = {f.name: f for f in self.store.tree()}
        self.assertEqual({"Mine", "Rock", "Live"}, set(by_name))
        self.assertEqual(by_name["Rock"].parent_id, mine.id)
        self.assertEqual(by_name["Live"].parent_id, by_name["Rock"].id)
        self.assertEqual(by_name["Mine"].count, 3)
        self.assertTrue(self.wait_for(lambda: db.find_by_location(SOURCE_LOCAL, str(library / "Rock" / "one.wav")) is not None))
        self.assertTrue(self.wait_for(lambda: len(db.query_ids(Scope(ufolders=tuple(self.store.subtree_ids(mine.id))))) == 3))
        w.sidebar.select("ufolder", mine.id)
        w._show_view("ufolder", mine.id)
        self.assertTrue(self.wait_for(lambda: w.table.track_model.rowCount() == 3))
        self.assertTrue((library / "loose.wav").exists())                                  # nothing was moved or deleted
        top = QMimeData()
        top.setUrls([QUrl.fromLocalFile(str(library / "Rock" / "Live"))])
        drag_through(self.sidebar, self.sidebar._headers["folders"], top)
        self.assertIn("Live", self.folder_rows())
        # a source that only offers "move" is refused rather than obeyed
        only_move = QDragMoveEvent(pos, Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(view, only_move)
        self.assertFalse(only_move.isAccepted())

    def test_a_folder_dragged_onto_another_moves_it(self):
        w = self.window
        self.names = ["A", "B", "C"]
        for _ in range(3):
            w._new_folder()
        by_name = {f.name: f for f in self.store.tree()}
        item = lambda name: self.sidebar._items[("ufolder", by_name[name].id)]
        folder_mime = lambda name: (lambda m: (m.setData(MIME_FOLDER, str(by_name[name].id).encode()), m)[1])(QMimeData())
        drag_through(self.sidebar, item("B"), folder_mime("A"), Qt.MoveAction, start_over=item("A"))
        self.assertEqual(self.store.get(by_name["A"].id).parent_id, by_name["B"].id)
        drag_through(self.sidebar, self.sidebar._headers["folders"], folder_mime("A"), Qt.MoveAction)
        self.assertIsNone(self.store.get(by_name["A"].id).parent_id)
        child = self.store.create("child", by_name["B"].id)
        w.refresh_folders()
        drag_through(self.sidebar, self.sidebar._items[("ufolder", by_name["B"].id)], folder_mime("B"), Qt.MoveAction)
        self.assertIn("inside itself", w.statusBar().currentMessage())
        self.assertEqual(self.store.get(child).parent_id, by_name["B"].id)

    def test_right_click_menus_of_a_folder(self):
        w = self.window
        self.names = ["Rock"]
        w._new_folder()
        folder = self.store.tree()[0]
        item = self.sidebar._items[("ufolder", folder.id)]
        captured = []
        original = QMenu.exec
        QMenu.exec = lambda menu, *a, **k: captured.append(menu)
        try:
            pos = self.sidebar.visualItemRect(item).center()
            self.sidebar.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, pos, self.sidebar.viewport().mapToGlobal(pos)))
            labels = [a.text() for a in captured[-1].actions() if a.text()]
            self.assertEqual(labels[:3], ["Play", "Shuffle", "Add to Queue"])
            for wanted in ("New Folder Inside…", "Rename", "Duplicate", "Sort Folders", "Delete"):
                self.assertIn(wanted, labels)
            self.assertNotIn("Show in File Manager", labels)
            sort = next(a for a in captured[-1].actions() if a.text() == "Sort Folders").menu()
            self.assertEqual([a.text() for a in sort.actions()], ["Name (A → Z)", "Name (Z → A)", "Number (1, 2, 10…)",
                                                                  "Number (10, 2, 1…)", "Newest First", "Oldest First"])
            self.assertTrue(sort.actions()[0].isChecked())
            head = self.sidebar.visualItemRect(self.sidebar._headers["folders"]).center()
            self.sidebar.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, head, self.sidebar.viewport().mapToGlobal(head)))
            self.assertEqual([a.text() for a in captured[-1].actions() if a.text()][:2], ["New Folder…", "Sort Folders"])
        finally:
            QMenu.exec = original

    def test_add_to_folder_submenu_lists_the_tree(self):
        w = self.window
        self.names = ["Party", "2019"]
        w._new_folder()
        w._new_folder(self.store.tree()[0].id)
        holder = QMenu()
        w.table._add_folder_menu(holder, [1, 2])
        root = holder.actions()[0].menu()
        self.assertEqual([a.text() for a in root.actions() if a.text()], ["Party", "New Folder…"])
        sub = next(a for a in root.actions() if a.text() == "Party").menu()
        sub.aboutToShow.emit()
        self.assertEqual([a.text() for a in sub.actions() if a.text()], ["This Folder", "2019"])

    def test_selecting_many_songs_with_the_keyboard_and_the_mouse(self):
        w = self.window
        table = w.table
        table.setFocus()
        pump(50)
        QTest.keyClick(table, Qt.Key_A, Qt.ControlModifier)                                # Ctrl+A: every song in the list
        self.assertEqual(len(table.selected_ids()), table.track_model.rowCount())
        table.clearSelection()
        cell = lambda row: table.visualRect(table.model().index(row, 0)).center()
        QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, cell(1))
        QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.ControlModifier, cell(4))     # Ctrl+click adds one more
        QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.ControlModifier, cell(6))
        self.assertEqual(sorted(i.row() for i in table.selectionModel().selectedRows()), [1, 4, 6])
        QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.ControlModifier, cell(4))     # Ctrl+click on a chosen one takes it off
        self.assertEqual(sorted(i.row() for i in table.selectionModel().selectedRows()), [1, 6])
        QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.NoModifier, cell(2))
        QTest.mouseClick(table.viewport(), Qt.LeftButton, Qt.ShiftModifier, cell(5))       # Shift+click: a range
        self.assertEqual(sorted(i.row() for i in table.selectionModel().selectedRows()), [2, 3, 4, 5])

    def test_duplicates_view_from_the_menu(self):
        w, db = self.window, self.db
        db.upsert_many([dict(source_type=SOURCE_LOCAL, location="/x/copy.mp3", title="Song 1", artist="Artist 1", album="Album 1",
                             genre="Rock", duration=90.5, bitrate=128, track_no=1)])
        finder = next(a for a in w.menu_button.menu().actions() if a.text() == "Find Duplicates").menu()
        self.assertEqual([a.text() for a in finder.actions()], ["Same Title, Artist and Album", "Exact Copies"])
        finder.actions()[0].trigger()
        self.assertEqual(w._view, ("duplicates", "same"))
        self.assertEqual(w.table.track_model.rowCount(), 2)
        self.assertEqual(w.title_label.text(), "Duplicates")
        self.assertIsNone(w.sidebar.current_key())
        w._show_view("duplicates", "exact")
        self.assertEqual(w.table.track_model.rowCount(), 0)
        self.assertEqual(w.table.empty_title, "No duplicates found")

    def test_music_juke_is_created_beside_the_music_and_the_scan_fills_it(self):
        w, db = self.window, self.db
        music = Path(helpers.ROOT) / "scan-music"
        for rel in ("Bachata/a.wav", "Bachata/b.wav", "Rock/c.wav"):
            (music / rel).parent.mkdir(parents=True, exist_ok=True)
            write_wav(music / rel, 0.2)
        self.cfg.set("music_dirs", [str(music)])
        w.start_scan()
        self.assertTrue(self.wait_for(lambda: w._scanner is None and db.count(SOURCE_LOCAL) >= 3))
        self.assertTrue(self.wait_for(lambda: {"Bachata", "Rock"} <= {f.name for f in self.store.tree()}))
        self.assertNotIn("scan-music", {f.name for f in self.store.tree()})       # the music directory is just where they live
        self.assertEqual(next(f for f in self.store.tree() if f.name == "Bachata").count, 2)
        self.assertEqual(self.folder_rows(), ["Bachata", "Rock"])
        self.assertTrue(self.store.path.exists())


if __name__ == "__main__":
    unittest.main()
