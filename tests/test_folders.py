import os
import tempfile
import unittest
from pathlib import Path

from . import helpers  # noqa: F401  (sets XDG env first)

from juke.db.database import SOURCE_LOCAL, Database, Scope
from juke.db.folders import FolderStore, default_path, music_dir, walk_audio
from .test_core import row


def make_music(root: Path) -> dict[str, Path]:
    """A small library on disk:  Music/{Bachata/{a.mp3,b.flac}, Rock/{c.ogg, Live/d.opus}, loose.wav}."""
    files = {}
    for rel in ("Bachata/a.mp3", "Bachata/b.flac", "Rock/c.ogg", "Rock/Live/d.opus", "loose.wav", "Notes/readme.txt"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        files[rel] = path
    return files


class FolderStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="juke-folders-"))
        self.music = self.tmp / "Music"
        self.files = make_music(self.music)
        self.store = FolderStore(self.tmp / "Music.juke")

    def test_creating_renaming_nesting_and_unique_names(self):
        a = self.store.create("Party")
        b = self.store.create("party")                              # same name at the same level, any case
        self.assertEqual(self.store.get(b).name, "party 2")
        child = self.store.create("2019", a)
        self.assertEqual(self.store.subtree_ids(a), [a, child])
        self.store.rename(child, "Summer")
        self.assertEqual(self.store.path_of(child), "Party / Summer")
        self.assertFalse(self.store.move(a, child))                 # a folder cannot go inside its own child
        self.assertTrue(self.store.move(child, None))
        self.assertIsNone(self.store.get(child).parent_id)
        self.store.delete(a)
        self.assertEqual({f.name for f in self.store.tree()}, {"party 2", "Summer"})

    def test_dropping_a_directory_keeps_its_layout_and_never_touches_the_files(self):
        home = self.store.create("Mine")
        added = self.store.add_paths(home, [str(self.music / "Rock"), str(self.files["loose.wav"]), str(self.files["Notes/readme.txt"])])
        self.assertEqual(sorted(os.path.basename(f) for f in added.files), ["c.ogg", "d.opus", "loose.wav"])   # the .txt is not music
        self.assertEqual(added.folders, 2)                          # Rock and Rock/Live
        by_name = {f.name: f for f in self.store.tree()}
        self.assertEqual(by_name["Rock"].count, 2)
        self.assertEqual(by_name["Live"].count, 1)
        self.assertEqual(by_name["Mine"].count, 3)                  # the folder's count includes everything below it
        self.assertEqual(self.store.items(home), [str(self.files["loose.wav"])])
        self.assertTrue(all(p.exists() for p in self.files.values()))
        self.assertIsNone(by_name["Rock"].source_path)              # an import is a copy of the layout, not a mirror
        again = self.store.add_paths(home, [str(self.files["loose.wav"])])   # dropping the same song twice adds it once
        self.assertEqual(len(self.store.items(home)), 1)
        self.assertEqual(again.files, [str(self.files["loose.wav"])])

    def test_a_directory_dropped_on_the_top_level_becomes_a_top_level_folder(self):
        added = self.store.add_paths(None, [str(self.music / "Rock"), str(self.files["loose.wav"])])
        self.assertEqual(sorted(os.path.basename(f) for f in added.files), ["c.ogg", "d.opus"])   # a loose song has no folder to sit in
        top = [f.name for f in self.store.tree() if f.parent_id is None]
        self.assertEqual(top, ["Rock"])

    def test_empty_directories_add_nothing_and_hidden_ones_inside_are_skipped(self):
        (self.music / "Empty").mkdir()
        hidden = self.music / "Bachata" / ".cache"
        hidden.mkdir()
        (hidden / "z.mp3").write_bytes(b"x")
        home = self.store.create("Mine")
        self.assertEqual(self.store.add_paths(home, [str(self.music / "Empty")]).files, [])
        self.assertEqual(self.store.add_paths(home, [str(self.music / "Bachata")]).files.__len__(), 2)   # a.mp3 and b.flac, not .cache/z.mp3
        self.assertNotIn(str(hidden / "z.mp3"), walk_audio(str(self.music)))

    def test_mirrored_folders_follow_the_disk(self):
        present = [str(p) for p in walk_audio(str(self.music))]
        self.assertTrue(self.store.sync_roots([str(self.music)], present))
        by_name = {f.name: f for f in self.store.tree()}
        self.assertEqual(set(by_name), {"Bachata", "Rock", "Live"})               # the music directory itself is not a folder
        self.assertIsNone(by_name["Bachata"].parent_id)
        self.assertEqual(by_name["Live"].parent_id, by_name["Rock"].id)
        self.assertEqual(by_name["Rock"].source_path, str(self.music / "Rock"))
        self.assertFalse(self.store.sync_roots([str(self.music)], present))          # nothing new: nothing changes
        # a new song appears, an old one is deleted
        new = self.music / "Bachata" / "new.mp3"
        new.write_bytes(b"x")
        self.files["Bachata/a.mp3"].unlink()
        present = [str(p) for p in walk_audio(str(self.music))]
        self.assertTrue(self.store.sync_roots([str(self.music)], present))
        bachata = next(f for f in self.store.tree() if f.name == "Bachata")
        self.assertEqual(sorted(os.path.basename(p) for p in self.store.items(bachata.id)), ["b.flac", "new.mp3"])

    def test_an_old_music_wrapper_folder_is_lifted_away_without_losing_anything(self):
        present = [str(p) for p in walk_audio(str(self.music))]
        conn = self.store.connect()
        with conn:                                        # what earlier versions made: the directory itself as a folder
            wrapper = conn.execute("INSERT INTO folders (parent_id, name, source_path, created_at) VALUES (NULL, 'Music', ?, 0)",
                                   (str(self.music),)).lastrowid
            rock = conn.execute("INSERT INTO folders (parent_id, name, source_path, created_at) VALUES (?, 'Rock', ?, 0)",
                                (wrapper, str(self.music / "Rock"))).lastrowid
            conn.execute("INSERT INTO hidden (path) VALUES (?)", (str(self.music),))
        self.store.sync_roots([str(self.music)], present)
        names = {f.name: f for f in self.store.tree()}
        self.assertNotIn("Music", names)
        self.assertIsNone(names["Rock"].parent_id)
        self.assertEqual(names["Rock"].id, rock)          # the very same folder, one level up
        self.assertIn("Bachata", names)                   # and what the old hide of the wrapper had swallowed is back

    def test_a_wrapper_holding_something_put_there_by_hand_is_kept(self):
        conn = self.store.connect()
        elsewhere = self.tmp / "Elsewhere.mp3"
        elsewhere.write_bytes(b"x")
        with conn:
            wrapper = conn.execute("INSERT INTO folders (parent_id, name, source_path, created_at) VALUES (NULL, 'Music', ?, 0)",
                                   (str(self.music),)).lastrowid
            conn.execute("INSERT INTO folder_items (folder_id, path) VALUES (?, ?)", (wrapper, str(elsewhere)))
        self.store.sync_roots([str(self.music)], [str(p) for p in walk_audio(str(self.music))])
        self.assertIn(str(elsewhere), self.store.items(wrapper))

    def test_music_juke_is_a_library_folder_with_one_database_file(self):
        from juke.db.folders import DB_NAME, README_NAME, VIEW_NAME, default_path

        music = self.tmp / "Home" / "Music"
        music.mkdir(parents=True)
        old = music / "Music.juke"                        # what earlier versions left: a lone database file
        legacy = FolderStore(old)
        legacy.create("Kept")
        legacy.close_thread_connection()
        os.environ["XDG_CONFIG_HOME"] = str(self.tmp / "nocfg")
        home, os.environ["HOME"] = os.environ.get("HOME"), str(self.tmp / "Home")
        try:
            db_file = default_path(self.tmp)
        finally:
            os.environ["HOME"] = home
        package = music / "Music.juke"
        self.assertEqual(db_file, package / DB_NAME)
        self.assertTrue(package.is_dir())
        self.assertTrue((package / README_NAME).exists())
        store = FolderStore(db_file)
        self.assertIn("Kept", {f.name for f in store.tree()})          # the old file's folders came along
        store.create("Anything")
        beside = sorted(p.name for p in package.iterdir() if p.name.startswith("folders.db"))
        self.assertEqual(beside, [DB_NAME])                             # no -wal, no -shm, no -journal left behind
        self.assertFalse(list(music.glob("Music.juke.*")))              # nothing stray in Music itself
        store.close_thread_connection()

    def test_the_folder_view_is_shortcuts_and_never_touches_real_files(self):
        from juke.db.folders import DB_NAME, VIEW_NAME, prepare_package

        package = prepare_package(self.tmp / "Lib" / "Music.juke")
        store = FolderStore(package / DB_NAME)
        party = store.create("Party")
        sub = store.create("Old / New", party)                            # a slash in a name cannot become a path
        song = str(self.files["Rock/c.ogg"])
        store.add_paths(party, [song])
        store.add_paths(sub, [song])
        self.assertEqual(store.write_view(), 2)
        link = package / VIEW_NAME / "Party" / "c.ogg"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), song)
        self.assertTrue((package / VIEW_NAME / "Party" / "Old _ New" / "c.ogg").is_symlink())
        (package / VIEW_NAME / "Party" / "mine.txt").write_text("hello")   # something the user put there
        store.remove_paths(party, [song])
        store.delete(sub)
        store.write_view()
        self.assertFalse(link.exists() or link.is_symlink())                # the shortcut is gone...
        self.assertFalse((package / VIEW_NAME / "Party" / "Old _ New").exists())
        self.assertTrue((package / VIEW_NAME / "Party" / "mine.txt").exists())   # ...a real file is left alone
        self.assertTrue(Path(song).exists())                                # and so are the songs themselves
        store.close_thread_connection()

    def test_the_scan_never_indexes_the_library_folder_itself(self):
        from juke.db.folders import DB_NAME, prepare_package

        package = prepare_package(self.music / "Music.juke")
        store = FolderStore(package / DB_NAME)
        folder = store.create("Everything")
        store.add_paths(folder, [str(self.files["Rock/c.ogg"])])
        store.write_view()
        self.assertTrue(list((package / "Folders").rglob("c.ogg")))         # a shortcut to a song sits inside the Music folder
        self.assertFalse([f for f in walk_audio(str(self.music)) if "Music.juke" in f])
        store.close_thread_connection()

    def test_sync_leaves_what_you_did_by_hand_alone(self):
        present = [str(p) for p in walk_audio(str(self.music))]
        self.store.sync_roots([str(self.music)], present)
        mine = self.store.create("Workout")
        self.store.add_paths(mine, [str(self.files["Rock/c.ogg"])])
        bachata = next(f for f in self.store.tree() if f.name == "Bachata")
        elsewhere = self.tmp / "Elsewhere" / "song.mp3"
        elsewhere.parent.mkdir()
        elsewhere.write_bytes(b"x")
        self.store.add_paths(bachata.id, [str(elsewhere)])                           # a song from outside, put into a mirrored folder
        self.files["Rock/c.ogg"].unlink()                                            # ...and one of Workout's songs disappears from the disk
        present = [str(p) for p in walk_audio(str(self.music))]
        self.store.sync_roots([str(self.music)], present)
        self.assertIn(str(elsewhere), self.store.items(bachata.id))                  # the hand-added song stays
        self.assertEqual(self.store.get(mine).name, "Workout")                       # and so does the folder made by hand
        # a whole directory removed: its mirrored folder goes when it holds nothing else
        for f in (self.music / "Rock" / "Live" / "d.opus",):
            f.unlink()
        present = [str(p) for p in walk_audio(str(self.music))]
        self.store.sync_roots([str(self.music)], present)
        self.assertNotIn("Live", {f.name for f in self.store.tree()})

    def test_nothing_is_locked_and_what_you_remove_stays_removed(self):
        present = [str(p) for p in walk_audio(str(self.music))]
        self.store.sync_roots([str(self.music)], present)
        by_name = {f.name: f for f in self.store.tree()}
        # any folder, mirrored or not, can be renamed, moved and deleted
        self.store.rename(by_name["Rock"].id, "Rock & Roll")
        self.assertTrue(self.store.move(by_name["Bachata"].id, by_name["Rock"].id))
        self.assertEqual(self.store.path_of(by_name["Bachata"].id), "Rock & Roll / Bachata")
        self.store.set_sort(by_name["Rock"].id, "number_desc")
        self.assertEqual(self.store.get(by_name["Rock"].id).sort_mode, "number_desc")
        # a song removed from a mirrored folder is not put back by the next scan
        rock = by_name["Rock"]
        c = str(self.files["Rock/c.ogg"])
        self.store.remove_paths(rock.id, [c])
        self.store.sync_roots([str(self.music)], present)
        self.assertNotIn(c, self.store.items(rock.id))
        # ...nor is a deleted folder
        live = next(f for f in self.store.tree() if f.name == "Live")
        self.store.delete(live.id)
        self.store.sync_roots([str(self.music)], present)
        self.assertNotIn("Live", {f.name for f in self.store.tree()})
        # until the user asks for everything back
        self.store.restore_hidden()
        self.store.sync_roots([str(self.music)], present)
        self.assertIn("Live", {f.name for f in self.store.tree()})
        self.assertIn(c, self.store.items(next(f for f in self.store.tree() if f.name == "Rock & Roll").id))

    def test_sorting_by_name_number_and_date_and_duplicating(self):
        from juke.db.folders import natural_key, ordered

        names = ["10 Pop", "2 Rock", "01 Salsa", "Bachata", "album 3", "Album 20"]
        store = self.store
        for n in names:
            store.create(n)
        tree = [f for f in store.tree() if f.parent_id is None]
        self.assertEqual([f.name for f in ordered(tree, "name")], ["01 Salsa", "10 Pop", "2 Rock", "Album 20", "album 3", "Bachata"])   # plain A-Z: "20" before "3"
        self.assertEqual([f.name for f in ordered(tree, "name_desc")][:2], ["Bachata", "album 3"])
        self.assertEqual([f.name for f in ordered(tree, "number")], ["01 Salsa", "2 Rock", "10 Pop", "album 3", "Album 20", "Bachata"])
        self.assertEqual([f.name for f in ordered(tree, "number_desc")][0], "Bachata")
        self.assertEqual([f.name for f in ordered(tree, "oldest")], names)                 # creation order
        self.assertEqual(natural_key("Track 2") < natural_key("Track 10"), True)
        store.set_sort(None, "number")
        self.assertEqual(store.root_sort(), "number")
        store.set_sort(None, "nonsense")
        self.assertEqual(store.root_sort(), "number")                                        # an unknown mode is ignored
        # duplicating copies the folder, what is in it and what is below it
        parent = store.create("Fiesta")
        store.create("Sub", parent)
        store.add_paths(parent, [str(self.files["loose.wav"])])
        copy = store.duplicate(parent)
        self.assertEqual(store.get(copy).name, "Fiesta 2")
        self.assertEqual(store.items(copy), [str(self.files["loose.wav"])])
        self.assertEqual(len(store.subtree_ids(copy)), 2)

    def test_default_location_is_the_music_folder_and_falls_back(self):
        home = Path(tempfile.mkdtemp(prefix="juke-home-"))
        old = {k: os.environ.get(k) for k in ("HOME", "XDG_CONFIG_HOME")}
        try:
            os.environ["HOME"] = str(home)
            os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
            self.assertEqual(music_dir(), home / "Music")
            self.assertEqual(default_path(), home / "Music" / "Music.juke" / "folders.db")
            (home / ".config").mkdir()
            (home / ".config" / "user-dirs.dirs").write_text('XDG_MUSIC_DIR="$HOME/Musica"\n')
            self.assertEqual(music_dir(), home / "Musica")                          # a translated Music folder is found
            (home / "Musica").mkdir()
            (home / "Musica").chmod(0o500)
            self.assertEqual(default_path(fallback_dir=self.tmp), self.tmp / "Music.juke" / "folders.db")   # cannot write there: use the fallback
        finally:
            (home / "Musica").chmod(0o700) if (home / "Musica").exists() else None
            for k, v in old.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


class LibraryFolderQueryTests(unittest.TestCase):
    def test_a_folder_lists_its_songs_and_those_below_it(self):
        tmp = Path(tempfile.mkdtemp(prefix="juke-scope-"))
        db = Database(tmp / "lib.db")
        store = FolderStore(tmp / "Music.juke")
        db.attach_folders(tmp / "Music.juke")
        db.upsert_many([row(i, location=f"/m/{i}.mp3") for i in range(6)])
        parent = store.create("Parent")
        child = store.create("Child", parent)
        store.add_paths(parent, [])                                               # nothing yet
        conn = store.connect()
        with conn:
            conn.executemany("INSERT INTO folder_items (folder_id, path) VALUES (?, ?)",
                             [(parent, "/m/0.mp3"), (parent, "/m/1.mp3"), (child, "/m/2.mp3"), (child, "/nowhere.mp3")])
        ids_of = lambda scope: [t.location for t in db.tracks_by_ids(db.query_ids(scope))]
        self.assertEqual(sorted(ids_of(Scope(ufolders=(child,)))), ["/m/2.mp3"])
        self.assertEqual(sorted(ids_of(Scope(ufolders=tuple(store.subtree_ids(parent))))), ["/m/0.mp3", "/m/1.mp3", "/m/2.mp3"])
        self.assertEqual(db.summary(Scope(ufolders=(parent, child)))[0], 3)
        self.assertEqual(len(db.query_ids(Scope(ufolders=(), ))), 0)              # a folder that does not exist shows nothing
        self.assertEqual(len(db.query_ids(Scope(ufolders=(parent,)), text="song 1")), 1)   # search works inside a folder

    def test_duplicates_are_found_by_song_and_by_exact_copy(self):
        tmp = Path(tempfile.mkdtemp(prefix="juke-dupes-"))
        db = Database(tmp / "lib.db")
        base = dict(artist="Aurora Vale", album="Glasshouse", duration=200.0)
        db.upsert_many([
            row(1, location="/a/paper.mp3", title="Paper Moons", bitrate=128, size=3_000_000, **{k: v for k, v in base.items() if k != "duration"}, duration=200.2),
            row(2, location="/b/paper.flac", title="paper moons", bitrate=900, size=30_000_000, **{k: v for k, v in base.items() if k != "duration"}, duration=200.1),   # same song, other case and format
            row(3, location="/c/paper-copy.mp3", title="Paper Moons", bitrate=128, size=3_000_000, **{k: v for k, v in base.items() if k != "duration"}, duration=200.3),  # a byte-for-byte copy of 1
            row(4, location="/d/other.mp3", title="Slow Motion Summer", **base),
            row(5, location="/e/nameless.mp3", title=""),
            row(6, location="/f/nameless2.mp3", title=""),
        ])
        ids = lambda mode: [t.location for t in db.tracks_by_ids(db.query_ids(Scope(duplicates=mode)))]
        self.assertEqual(ids("same"), ["/b/paper.flac", "/a/paper.mp3", "/c/paper-copy.mp3"])     # together, best quality first
        self.assertEqual(sorted(ids("exact")), ["/a/paper.mp3", "/c/paper-copy.mp3"])              # only the true copies
        self.assertEqual(db.summary(Scope(duplicates="same"))[0], 3)                               # untitled songs are never "duplicates"

    def test_without_the_file_attached_a_folder_scope_is_just_empty(self):
        tmp = Path(tempfile.mkdtemp(prefix="juke-scope2-"))
        db = Database(tmp / "lib.db")
        db.upsert_many([row(1, location="/m/1.mp3")])
        self.assertEqual(db.query_ids(Scope(ufolders=(1,))), [])
        self.assertEqual(len(db.query_ids()), 1)


if __name__ == "__main__":
    unittest.main()


class ScanKeepsSongsFromElsewhereTests(unittest.TestCase):
    def test_a_song_opened_from_outside_the_music_folders_survives_the_startup_scan(self):
        from juke.db.indexer import LibraryScanner
        tmp = Path(tempfile.mkdtemp(prefix="juke-scan-"))
        music, elsewhere = tmp / "Music", tmp / "Downloads"
        music.mkdir()
        elsewhere.mkdir()
        inside, outside = music / "a.mp3", elsewhere / "b.mp3"
        inside.write_bytes(b"x")
        outside.write_bytes(b"x")
        db = Database(tmp / "lib.db")
        db.upsert_many([row(1, location=str(inside)), row(2, location=str(outside))])
        LibraryScanner(db, [str(music)])._scan()                       # a scan of Music only
        kept = {t.location for t in db.tracks_by_ids(db.query_ids())}
        self.assertIn(str(outside), kept)                              # still there: its file exists
        outside.unlink()
        inside.unlink()
        LibraryScanner(db, [str(music)])._scan()
        self.assertEqual({t.location for t in db.tracks_by_ids(db.query_ids())}, set())   # both gone from disk: both go
