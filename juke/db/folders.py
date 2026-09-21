"""Music.juke: the folders you organise your music in.

A small SQLite file that lives in the user's Music folder, next to the music, so the organisation
travels with it. It holds a tree of folders and, in each, the *paths* of the songs it contains; the
audio itself is never copied or moved.

* Folders that mirror a directory on disk carry its path (``source_path``). They are kept in step
  with the disk each time the library is scanned: new songs appear, removed ones go away.
* Folders you create, or that come from dropping something in, have no ``source_path`` and are
  never touched by that synchronisation.
* Nothing is locked. Any folder can be renamed, moved, sorted or deleted. What you delete from a
  mirrored folder is remembered (``hidden``) so the next scan does not bring it back.

The library database attaches this file (as ``mj``) so a folder can be listed with one query.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from ..config import AUDIO_EXTENSIONS

PACKAGE_NAME = "Music.juke"     # a folder in the user's Music folder that reads as one library, opened like any other folder
DB_NAME = "folders.db"          # the organization itself, the only file Juke depends on
VIEW_NAME = "Folders"           # what the organization looks like, as folders of shortcuts to the songs
README_NAME = "README.txt"

README = """Music.juke - Juke's library
===========================

This is where Juke keeps how your music is organized: the folders you see in
Juke's sidebar and what is in each of them.

  folders.db   the organization (one small file). Juke reads and writes it.
  Folders/     the same organization as ordinary folders, so you can look at it
               from the file manager. Each song is a shortcut to the real file.
               Juke keeps it up to date; change things in Juke, not here.

Your music files are NOT in here and Juke never moves, renames or deletes them.
Removing something from Juke only removes it from this organization.

Music.juke - la biblioteca de Juke
==================================

Aqui Juke guarda como esta organizada tu musica: las carpetas del panel lateral
y lo que hay en cada una.

  folders.db   la organizacion (un archivo pequeno). Juke lo lee y lo escribe.
  Folders/     la misma organizacion como carpetas normales, para verla desde el
               explorador de archivos. Cada cancion es un acceso directo al
               archivo real. Juke lo mantiene al dia; los cambios se hacen en Juke.

Tus archivos de musica NO estan aqui y Juke nunca los mueve, renombra ni borra.
Quitar algo de Juke solo lo quita de esta organizacion.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id   INTEGER REFERENCES folders (id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    source_path TEXT,
    sort_mode   TEXT    NOT NULL DEFAULT 'name',
    created_at  REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders (parent_id);
CREATE INDEX IF NOT EXISTS idx_folders_source ON folders (source_path) WHERE source_path IS NOT NULL;
CREATE TABLE IF NOT EXISTS folder_items (
    folder_id INTEGER NOT NULL REFERENCES folders (id) ON DELETE CASCADE,
    path      TEXT    NOT NULL,
    added_at  REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (folder_id, path)
);
CREATE INDEX IF NOT EXISTS idx_folder_items_path ON folder_items (path);
CREATE TABLE IF NOT EXISTS hidden (
    path TEXT PRIMARY KEY
);
"""


# How the folders directly inside a folder (or at the top) are ordered.
SORT_MODES = ("name", "name_desc", "number", "number_desc", "newest", "oldest")


@dataclass(frozen=True, slots=True)
class Folder:
    id: int
    parent_id: int | None
    name: str
    source_path: str | None
    count: int          # songs in this folder and everything below it
    sort_mode: str = "name"   # how *its* sub-folders are ordered
    created_at: float = 0.0


def natural_key(text: str):
    """Sort key that reads numbers as numbers: "Track 2" < "Track 10", "01 Rock" < "2 Pop"."""
    import re

    return [(0, int(part), "") if part.isdigit() else (1, 0, part.casefold()) for part in re.split(r"(\d+)", text) if part != ""]


def ordered(folders: list[Folder], mode: str) -> list[Folder]:
    """``folders`` (siblings) in ``mode`` order."""
    if mode in ("newest", "oldest"):
        return sorted(folders, key=lambda f: (f.created_at, f.id), reverse=mode == "newest")
    key = (lambda f: natural_key(f.name)) if mode.startswith("number") else (lambda f: f.name.casefold())
    return sorted(folders, key=key, reverse=mode.endswith("_desc"))


@dataclass(frozen=True, slots=True)
class Removed:
    """What deleting a folder takes out of the library (never out of the disk)."""
    dirs: list[str]
    orphans: list[str]


@dataclass(slots=True)
class Added:
    """What a drop did: the audio files now in the folder (for the library to index) and the new sub-folders."""

    files: list[str]
    folders: int


def music_dir() -> Path:
    """The user's Music folder (XDG user-dirs when set, ``~/Music`` otherwise)."""
    dirs = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "user-dirs.dirs"
    try:
        for line in dirs.read_text().splitlines():
            if line.startswith("XDG_MUSIC_DIR="):
                value = line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(Path.home()))
                if value:
                    return Path(value)
    except OSError:
        pass
    return Path.home() / "Music"


def default_path(fallback_dir: Path | None = None) -> Path:
    """The organization's database: ``Music/Music.juke/folders.db``. Music.juke always lives in the Music folder;
    only if that cannot be written to at all does it go to ``fallback_dir``."""
    target = music_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        if os.access(target, os.W_OK):
            return prepare_package(target / PACKAGE_NAME) / DB_NAME
    except OSError:
        pass
    return prepare_package((fallback_dir or Path.home()) / PACKAGE_NAME) / DB_NAME


def prepare_package(package: Path) -> Path:
    """Make sure ``package`` is a Music.juke folder with its README. Earlier versions kept Music.juke as a single
    database file: that file moves inside, so nothing is lost."""
    if package.is_file():
        try:
            old = sqlite3.connect(package, timeout=30)
            old.execute("PRAGMA journal_mode=DELETE")      # fold in whatever a former WAL file still held
            old.close()
        except sqlite3.Error:
            pass
        moved = package.with_name(package.name + ".moving")
        os.replace(package, moved)
        package.mkdir()
        os.replace(moved, package / DB_NAME)
        for side in ("-wal", "-shm", "-journal"):
            try:
                package.with_name(package.name + side).unlink()
            except OSError:
                pass
    package.mkdir(parents=True, exist_ok=True)
    readme = package / README_NAME
    if not readme.exists():
        try:
            readme.write_text(README, encoding="utf-8")
        except OSError:
            pass
    return package


def _safe_name(name: str) -> str:
    """A folder or song name that is fine as a file name (no slash, not hidden, not empty)."""
    cleaned = name.replace(os.sep, "_").replace("\0", "").strip() or "_"
    return "_" + cleaned if cleaned.startswith(".") else cleaned


def _is_audio(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS


def walk_audio(root: str) -> list[str]:
    """Every audio file below ``root`` (hidden directories skipped, symlink loops safe)."""
    found: list[str] = []
    seen: set[tuple[int, int]] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            stat = os.stat(current)
            if (stat.st_dev, stat.st_ino) in seen:
                continue
            seen.add((stat.st_dev, stat.st_ino))
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=True):
                            if not entry.name.startswith(".") and not entry.name.endswith(".juke"):
                                stack.append(entry.path)
                        elif _is_audio(entry.name):
                            found.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return found


class FolderStore:
    """Thread-safe (one connection per thread) access to a Music.juke file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        conn = self.connect()
        conn.executescript(SCHEMA)
        if "sort_mode" not in {r[1] for r in conn.execute("PRAGMA table_info(folders)")}:
            conn.execute("ALTER TABLE folders ADD COLUMN sort_mode TEXT NOT NULL DEFAULT 'name'")
        conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('created', ?)", (str(time.time()),))
        conn.commit()

    def connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30)
            # One file, nothing beside it: the -wal and -shm files of WAL mode invite someone to tidy them away
            # and take the folders with them. (An older Music.juke in WAL mode is converted on first open.)
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def close_thread_connection(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -- reading -----------------------------------------------------------------------------
    def tree(self) -> list[Folder]:
        """Every folder, with the number of songs at and below it."""
        conn = self.connect()
        rows = conn.execute("SELECT id, parent_id, name, source_path, sort_mode, created_at FROM folders").fetchall()
        own = dict(conn.execute("SELECT folder_id, COUNT(*) FROM folder_items GROUP BY folder_id"))
        children: dict[int | None, list[int]] = {}
        for fid, parent, *_ in rows:
            children.setdefault(parent, []).append(fid)
        totals: dict[int, int] = {}
        # counts from the leaves up, without recursion (a deep tree must not hit the interpreter's limit)
        order = []
        stack = list(children.get(None, ()))
        while stack:
            fid = stack.pop()
            order.append(fid)
            stack.extend(children.get(fid, ()))
        for fid in reversed(order):
            totals[fid] = own.get(fid, 0) + sum(totals[c] for c in children.get(fid, ()))

        def total(fid: int) -> int:
            return totals.get(fid, own.get(fid, 0))

        return [Folder(fid, parent, name, source, total(fid), mode, created) for fid, parent, name, source, mode, created in rows]

    def get(self, folder_id: int) -> Folder | None:
        return next((f for f in self.tree() if f.id == folder_id), None)

    def is_empty(self) -> bool:
        return self.connect().execute("SELECT 1 FROM folders LIMIT 1").fetchone() is None

    def subtree_ids(self, folder_id: int) -> list[int]:
        """``folder_id`` and every folder below it."""
        rows = self.connect().execute(
            "WITH RECURSIVE sub(id) AS (SELECT ? UNION ALL SELECT f.id FROM folders f JOIN sub ON f.parent_id = sub.id) "
            "SELECT id FROM sub", (folder_id,)).fetchall()
        return [r[0] for r in rows]

    def items(self, folder_id: int) -> list[str]:
        return [r[0] for r in self.connect().execute("SELECT path FROM folder_items WHERE folder_id=? ORDER BY path", (folder_id,))]

    def path_of(self, folder_id: int) -> str:
        """"Music / Bachata / 2019" for headings and messages."""
        by_id = {f.id: f for f in self.tree()}
        parts: list[str] = []
        node = by_id.get(folder_id)
        while node is not None:
            parts.append(node.name)
            node = by_id.get(node.parent_id) if node.parent_id else None
        return " / ".join(reversed(parts))

    # -- editing folders -----------------------------------------------------------------------
    def _unique_name(self, conn: sqlite3.Connection, parent_id: int | None, name: str, ignore: int | None = None) -> str:
        name = name.strip() or "Folder"
        taken = {r[0].casefold() for r in conn.execute(
            "SELECT name FROM folders WHERE parent_id IS ? AND id IS NOT ?", (parent_id, ignore))}
        candidate, n = name, 2
        while candidate.casefold() in taken:
            candidate, n = f"{name} {n}", n + 1
        return candidate

    def create(self, name: str, parent_id: int | None = None, source_path: str | None = None) -> int:
        conn = self.connect()
        with conn:
            return conn.execute(
                "INSERT INTO folders (parent_id, name, source_path, created_at) VALUES (?, ?, ?, ?)",
                (parent_id, self._unique_name(conn, parent_id, name), source_path, time.time())).lastrowid

    def rename(self, folder_id: int, name: str) -> None:
        conn = self.connect()
        row = conn.execute("SELECT parent_id FROM folders WHERE id=?", (folder_id,)).fetchone()
        if row is None:
            return
        with conn:
            conn.execute("UPDATE folders SET name=? WHERE id=?", (self._unique_name(conn, row[0], name, folder_id), folder_id))

    def delete(self, folder_id: int, roots: Sequence[str] = ()) -> Removed:
        """Remove the folder, its sub-folders and what they list. The music files are not touched.

        A folder that mirrors a directory is remembered as removed, so the next scan leaves it out. What the
        caller must take out of the library is returned: the directories that were mirrored, and the songs
        brought in from outside ``roots`` that no other folder lists any more.
        """
        conn = self.connect()
        sub = ("WITH RECURSIVE sub(id) AS (SELECT ? UNION ALL SELECT f.id FROM folders f JOIN sub ON f.parent_id = sub.id) "
               "SELECT %s FROM %s WHERE %s IN (SELECT id FROM sub)")
        roots = [os.path.abspath(r) for r in roots if r]
        with conn:
            dirs = [r[0] for r in conn.execute(sub % ("source_path", "folders", "id") + " AND source_path IS NOT NULL", (folder_id,))]
            listed = [r[0] for r in conn.execute(sub % ("path", "folder_items", "folder_id"), (folder_id,))]
            for source in dirs:
                conn.execute("INSERT OR IGNORE INTO hidden (path) VALUES (?)", (source,))
            conn.execute("DELETE FROM folders WHERE id=?", (folder_id,))
            still = {r[0] for start in range(0, len(listed), 500)
                     for r in conn.execute(f"SELECT path FROM folder_items WHERE path IN ({','.join('?' * len(listed[start:start + 500]))})",
                                           listed[start:start + 500])}
        orphans = [p for p in dict.fromkeys(listed)
                   if p not in still and not any(p.startswith(r + os.sep) for r in roots)]
        return Removed(dirs=dirs, orphans=orphans)

    def write_view(self) -> int:
        """Lay the organization out as folders of shortcuts under ``Music.juke/Folders`` so it can be browsed from the
        file manager. Only shortcuts and empty folders that Juke made are ever removed; a real file put there stays.
        Safe to call from a worker thread. Returns how many shortcuts the view holds."""
        package = self.path.parent
        if not package.name.endswith(".juke"):
            return 0
        view = package / VIEW_NAME
        conn = self.connect()
        folders = self.tree()
        by_id = {f.id: f for f in folders}
        rel_of: dict[int, str] = {}

        def rel(folder: Folder) -> str:
            if folder.id not in rel_of:
                up = rel(by_id[folder.parent_id]) if folder.parent_id in by_id else ""
                name = _safe_name(folder.name)
                rel_of[folder.id] = os.path.join(up, name) if up else name
            return rel_of[folder.id]

        dirs = {rel(f) for f in folders}
        wanted: dict[str, str] = {}
        taken: dict[int, set[str]] = {}
        for folder_id, path in conn.execute("SELECT folder_id, path FROM folder_items ORDER BY folder_id, path"):
            if folder_id not in by_id:
                continue
            names = taken.setdefault(folder_id, set())
            base = _safe_name(os.path.basename(path))
            stem, ext = os.path.splitext(base)
            name, n = base, 2
            while name.casefold() in names:
                name, n = f"{stem} ({n}){ext}", n + 1
            names.add(name.casefold())
            wanted[os.path.join(rel(by_id[folder_id]), name)] = path

        view.mkdir(parents=True, exist_ok=True)
        for directory in sorted(dirs):
            (view / directory).mkdir(parents=True, exist_ok=True)
        for link, target in wanted.items():
            spot = view / link
            if spot.is_symlink():
                if os.readlink(spot) == target:
                    continue
                spot.unlink()
            elif spot.exists():
                continue                                          # not ours: leave it alone
            try:
                os.symlink(target, spot)
            except OSError:
                continue
        for current, subdirs, files in os.walk(view, topdown=False):
            for entry in files + subdirs:
                full = os.path.join(current, entry)
                if os.path.islink(full) and os.path.relpath(full, view) not in wanted:
                    try:
                        os.unlink(full)
                    except OSError:
                        pass
            here = os.path.relpath(current, view)
            if here != "." and here not in dirs:
                try:
                    os.rmdir(current)                            # only succeeds when nothing is left in it
                except OSError:
                    pass
        return len(wanted)

    def hidden_dirs(self) -> list[str]:
        """Directories the user removed from Juke (a hidden *song* is not one): the scanner must not bring them back."""
        return [r[0] for r in self.connect().execute("SELECT path FROM hidden") if Path(r[0]).suffix.lower() not in AUDIO_EXTENSIONS]

    def restore_hidden(self) -> None:
        """Forget what was removed from the mirrored folders: the next scan brings it all back."""
        conn = self.connect()
        with conn:
            conn.execute("DELETE FROM hidden")

    def move(self, folder_id: int, new_parent_id: int | None) -> bool:
        """Put a folder inside another (or at the top). False if that would put it inside itself."""
        if new_parent_id is not None and new_parent_id in self.subtree_ids(folder_id):
            return False
        conn = self.connect()
        row = conn.execute("SELECT name, parent_id FROM folders WHERE id=?", (folder_id,)).fetchone()
        if row is None or row[1] == new_parent_id:
            return row is not None
        with conn:
            conn.execute("UPDATE folders SET parent_id=?, name=? WHERE id=?",
                         (new_parent_id, self._unique_name(conn, new_parent_id, row[0], folder_id), folder_id))
        return True

    def set_sort(self, folder_id: int | None, mode: str) -> None:
        """How the folders inside ``folder_id`` (None: the top level) are ordered."""
        if mode not in SORT_MODES:
            return
        conn = self.connect()
        with conn:
            if folder_id is None:
                conn.execute("INSERT INTO meta (key, value) VALUES ('root_sort', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (mode,))
            else:
                conn.execute("UPDATE folders SET sort_mode=? WHERE id=?", (mode, folder_id))

    def root_sort(self) -> str:
        row = self.connect().execute("SELECT value FROM meta WHERE key='root_sort'").fetchone()
        return row[0] if row and row[0] in SORT_MODES else "name"

    def duplicate(self, folder_id: int) -> int | None:
        """A copy of the folder with everything in it, next to the original ("Rock 2")."""
        conn = self.connect()
        source = conn.execute("SELECT parent_id, name, sort_mode FROM folders WHERE id=?", (folder_id,)).fetchone()
        if source is None:
            return None
        now = time.time()
        with conn:
            def copy(old: int, parent: int | None, name: str, mode: str) -> int:
                new = conn.execute("INSERT INTO folders (parent_id, name, sort_mode, created_at) VALUES (?, ?, ?, ?)",
                                   (parent, self._unique_name(conn, parent, name), mode, now)).lastrowid
                conn.execute("INSERT INTO folder_items (folder_id, path, added_at) SELECT ?, path, ? FROM folder_items WHERE folder_id=?",
                             (new, now, old))
                for child, child_name, child_mode in conn.execute(
                        "SELECT id, name, sort_mode FROM folders WHERE parent_id=?", (old,)).fetchall():
                    copy(child, new, child_name, child_mode)
                return new

            return copy(folder_id, source[0], source[1], source[2])

    # -- editing contents ------------------------------------------------------------------------
    def add_paths(self, folder_id: int | None, paths: Iterable[str]) -> Added:
        """Put songs and whole folders (as sub-folders, keeping their layout) into ``folder_id``.

        With ``folder_id`` None (the top level) only directories can be added: a song needs a folder to sit in.
        """
        conn = self.connect()
        added = Added(files=[], folders=0)
        now = time.time()
        with conn:
            for raw in paths:
                path = os.path.abspath(raw)
                if os.path.isdir(path):
                    self._import_dir(conn, folder_id, path, added, now)
                elif folder_id is not None and os.path.isfile(path) and _is_audio(path):
                    conn.execute("INSERT OR IGNORE INTO folder_items (folder_id, path, added_at) VALUES (?, ?, ?)", (folder_id, path, now))
                    added.files.append(path)
        return added

    def _import_dir(self, conn: sqlite3.Connection, parent_id: int | None, directory: str, added: Added, now: float) -> None:
        files = walk_audio(directory)
        if not files:
            return
        made: dict[str, int] = {}

        def folder_for(dirpath: str) -> int:
            if dirpath in made:
                return made[dirpath]
            if dirpath == directory:
                up = parent_id
            else:
                up = folder_for(os.path.dirname(dirpath))
            made[dirpath] = conn.execute(
                "INSERT INTO folders (parent_id, name, created_at) VALUES (?, ?, ?)",
                (up, self._unique_name(conn, up, os.path.basename(dirpath)), now)).lastrowid
            added.folders += 1
            return made[dirpath]

        rows = []
        for file in sorted(files, key=str.casefold):
            rows.append((folder_for(os.path.dirname(file)), file, now))
            added.files.append(file)
        conn.executemany("INSERT OR IGNORE INTO folder_items (folder_id, path, added_at) VALUES (?, ?, ?)", rows)

    def remove_paths(self, folder_id: int, paths: Sequence[str]) -> None:
        conn = self.connect()
        with conn:
            source = conn.execute("SELECT source_path FROM folders WHERE id=?", (folder_id,)).fetchone()
            if source and source[0]:                      # a song taken out of a mirrored folder stays out
                conn.executemany("INSERT OR IGNORE INTO hidden (path) VALUES (?)",
                                 [(p,) for p in paths if os.path.dirname(p) == source[0]])
            for start in range(0, len(paths), 500):
                chunk = list(paths[start:start + 500])
                conn.execute(f"DELETE FROM folder_items WHERE folder_id=? AND path IN ({','.join('?' * len(chunk))})", (folder_id, *chunk))

    # -- keeping the mirrored folders in step with the disk -----------------------------------------
    def _lift_music_dirs(self, conn: sqlite3.Connection, roots: Sequence[str]) -> bool:
        """Older versions showed the music directory itself as a folder ("Music"). It is only the place the
        folders live in now, so what was inside comes up a level and the empty wrapper goes away. A wrapper
        that holds something put there by hand is left as it is."""
        changed = False
        with conn:
            if roots:
                conn.execute(f"DELETE FROM hidden WHERE path IN ({','.join('?' * len(roots))})", roots)
            for root in roots:
                row = conn.execute("SELECT id FROM folders WHERE source_path=?", (root,)).fetchone()
                if row is None:
                    continue
                wrapper = row[0]
                if any(os.path.dirname(p[0]) != root for p in conn.execute("SELECT path FROM folder_items WHERE folder_id=?", (wrapper,))):
                    continue
                for child, name in conn.execute("SELECT id, name FROM folders WHERE parent_id=?", (wrapper,)).fetchall():
                    conn.execute("UPDATE folders SET parent_id=NULL, name=? WHERE id=?", (self._unique_name(conn, None, name, child), child))
                conn.execute("DELETE FROM folders WHERE id=?", (wrapper,))
                changed = True
        return changed

    def sync_roots(self, roots: Sequence[str], present: Iterable[str]) -> bool:
        """Make the folders that mirror ``roots`` match ``present`` (the audio files found there).

        New directories become folders, new songs appear in them, songs that vanished leave. Anything
        you put there by hand, and every folder you made yourself, is left alone. Returns True if
        something changed.
        """
        conn = self.connect()
        roots = [os.path.abspath(r) for r in roots if r]
        changed = self._lift_music_dirs(conn, roots)
        hidden = {r[0] for r in conn.execute("SELECT path FROM hidden")}
        skip = tuple(h + os.sep for h in hidden)
        files = sorted((f for f in set(present) if f not in hidden and not f.startswith(skip)), key=str.casefold)
        now = time.time()
        with conn:
            mirrored = {src: fid for fid, src in conn.execute("SELECT id, source_path FROM folders WHERE source_path IS NOT NULL")}
            wanted: dict[str, list[str]] = {}
            for file in files:
                for root in roots:
                    if file.startswith(root + os.sep):
                        wanted.setdefault(os.path.dirname(file), []).append(file)
                        break

            def folder_for(dirpath: str) -> int | None:
                """The folder mirroring ``dirpath``; None for a music directory itself, which is just where the folders live."""
                nonlocal changed
                if dirpath in mirrored:
                    return mirrored[dirpath]
                if dirpath in roots:
                    return None
                up = folder_for(os.path.dirname(dirpath))
                mirrored[dirpath] = conn.execute(
                    "INSERT INTO folders (parent_id, name, source_path, created_at) VALUES (?, ?, ?, ?)",
                    (up, self._unique_name(conn, up, os.path.basename(dirpath) or dirpath), dirpath, now)).lastrowid
                changed = True
                return mirrored[dirpath]

            have: set[tuple[int, str]] = set(conn.execute("SELECT folder_id, path FROM folder_items"))
            fresh: list[tuple[int, str, float]] = []
            for dirpath, listed in wanted.items():
                fid = folder_for(dirpath)
                if fid is None:                                   # songs loose in the music directory: they stay in the Library
                    continue
                for file in listed:
                    if (fid, file) not in have:
                        fresh.append((fid, file, now))
            if fresh:
                conn.executemany("INSERT OR IGNORE INTO folder_items (folder_id, path, added_at) VALUES (?, ?, ?)", fresh)
                changed = True

            # songs that left a mirrored directory; hand-added ones (from elsewhere) stay
            gone: list[tuple[int, str]] = []
            existing = set(files)
            for dirpath, fid in mirrored.items():
                if not any(dirpath == r or dirpath.startswith(r + os.sep) for r in roots):
                    continue
                for (folder_id, path) in have:
                    if folder_id == fid and os.path.dirname(path) == dirpath and path not in existing:
                        gone.append((fid, path))
            if gone:
                conn.executemany("DELETE FROM folder_items WHERE folder_id=? AND path=?", gone)
                changed = True

            # mirrored folders whose directory is gone and that hold nothing any more
            for dirpath, fid in list(mirrored.items()):
                if dirpath in wanted or not any(dirpath.startswith(r + os.sep) for r in roots):
                    continue
                busy = conn.execute("SELECT 1 FROM folder_items WHERE folder_id=? LIMIT 1", (fid,)).fetchone() \
                    or conn.execute("SELECT 1 FROM folders WHERE parent_id=? LIMIT 1", (fid,)).fetchone()
                if not busy:
                    conn.execute("DELETE FROM folders WHERE id=?", (fid,))
                    changed = True
        return changed
