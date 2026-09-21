"""SQLite library shared by local files and Airsonic tracks.

Every track, wherever it comes from, is one row with the same metadata. The
player only resolves a playable URL when Play is pressed (see audio/sources.py).

The GUI never holds the whole library in memory: it asks for ordered id lists
(:meth:`Database.query_ids`) and fetches rows page by page
(:meth:`Database.tracks_by_ids`).
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

SOURCE_LOCAL = "local"
SOURCE_AIRSONIC = "airsonic"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type  TEXT    NOT NULL,
    location     TEXT    NOT NULL,
    title        TEXT    NOT NULL DEFAULT '',
    artist       TEXT    NOT NULL DEFAULT '',
    album        TEXT    NOT NULL DEFAULT '',
    genre        TEXT    NOT NULL DEFAULT '',
    year         INTEGER NOT NULL DEFAULT 0,
    track_no     INTEGER NOT NULL DEFAULT 0,
    duration     REAL    NOT NULL DEFAULT 0,
    bitrate      INTEGER NOT NULL DEFAULT 0,
    cover_key    TEXT    NOT NULL DEFAULT '',
    search_text  TEXT    NOT NULL DEFAULT '',
    folder       TEXT    NOT NULL DEFAULT '',
    mtime        REAL    NOT NULL DEFAULT 0,
    size         INTEGER NOT NULL DEFAULT 0,
    favorite     INTEGER NOT NULL DEFAULT 0,
    play_count   INTEGER NOT NULL DEFAULT 0,
    last_played  REAL    NOT NULL DEFAULT 0,
    added_at     REAL    NOT NULL DEFAULT 0,
    UNIQUE (source_type, location)
);
CREATE INDEX IF NOT EXISTS idx_tracks_artist      ON tracks (artist COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_album       ON tracks (album COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_title       ON tracks (title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_genre       ON tracks (genre COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_source_type ON tracks (source_type);
CREATE INDEX IF NOT EXISTS idx_tracks_natural     ON tracks (artist COLLATE NOCASE, album COLLATE NOCASE, track_no, title COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_favorite    ON tracks (favorite) WHERE favorite = 1;
CREATE INDEX IF NOT EXISTS idx_tracks_last_played ON tracks (last_played) WHERE last_played > 0;
CREATE TABLE IF NOT EXISTS playlists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    created_at  REAL    NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists (id) ON DELETE CASCADE,
    track_id    INTEGER NOT NULL REFERENCES tracks (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, position)
);
CREATE INDEX IF NOT EXISTS idx_playlist_tracks_track ON playlist_tracks (track_id);
CREATE TABLE IF NOT EXISTS stations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    stream_url  TEXT    NOT NULL UNIQUE,
    homepage    TEXT    NOT NULL DEFAULT '',
    favicon     TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '',
    country     TEXT    NOT NULL DEFAULT '',
    codec       TEXT    NOT NULL DEFAULT '',
    bitrate     INTEGER NOT NULL DEFAULT 0,
    uuid        TEXT    NOT NULL DEFAULT '',
    source_url  TEXT    NOT NULL DEFAULT '',
    added_at    REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_stations_name ON stations (name COLLATE NOCASE);
"""

_COLUMNS = (
    "id, source_type, location, title, artist, album, genre, year, track_no, "
    "duration, bitrate, cover_key, favorite, play_count, last_played"
)

# Sortable columns of the track table -> SQL ordering expression.
SORT_EXPRESSIONS = {
    "title": "title COLLATE NOCASE",
    "artist": "artist COLLATE NOCASE",
    "album": "album COLLATE NOCASE",
    "duration": "duration",
    "genre": "genre COLLATE NOCASE",
    "bitrate": "bitrate",
    "source": "source_type",
}
NATURAL_ORDER = "artist COLLATE NOCASE, album COLLATE NOCASE, track_no, title COLLATE NOCASE"

_UPSERT_FIELDS = (
    "source_type", "location", "title", "artist", "album", "genre", "year", "track_no",
    "duration", "bitrate", "cover_key", "search_text", "mtime", "size", "folder",
)


def normalize(text: str) -> str:
    """Lower-case and strip accents so that "cancion" finds "Canción"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def search_text_for(title: str, artist: str, album: str, genre: str) -> str:
    return normalize(f"{title} {artist} {album} {genre}")


@dataclass(slots=True)
class Track:
    id: int
    source_type: str
    location: str  # absolute file path (local) or server-side song id (airsonic)
    title: str
    artist: str
    album: str
    genre: str
    year: int
    track_no: int
    duration: float
    bitrate: int
    cover_key: str
    favorite: bool
    play_count: int
    last_played: float

    @classmethod
    def from_row(cls, row: Sequence) -> "Track":
        return cls(
            row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8],
            row[9], row[10], row[11], bool(row[12]), row[13], row[14],
        )

    @property
    def is_local(self) -> bool:
        return self.source_type == SOURCE_LOCAL


@dataclass(slots=True)
class Station:
    """An internet radio station. ``id`` is 0 for one that is not saved (e.g. a search result)."""

    id: int
    name: str
    stream_url: str
    homepage: str = ""
    favicon: str = ""
    tags: str = ""
    country: str = ""
    codec: str = ""
    bitrate: int = 0
    uuid: str = ""
    source_url: str = ""    # the page / playlist the user gave: stations change their stream address, so keep where to find it again

    @property
    def saved(self) -> bool:
        return self.id > 0


@dataclass(frozen=True, slots=True)
class Scope:
    """Which slice of the library a view shows."""

    source_type: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    folder: str | None = None  # server-side folder path; includes its sub-folders
    ufolders: tuple[int, ...] | None = None  # ids of the user's folders (Music.juke): the folder and everything below it
    duplicates: str | None = None  # "same": same title, artist and album; "exact": and the same length and size
    favorites: bool = False
    recent: bool = False


class Database:
    """Thread-safe (one connection per thread) SQLite wrapper, WAL mode."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._folders_file: Path | None = None
        conn = self.connect()
        conn.executescript(SCHEMA)
        self._migrate(conn)

    def attach_folders(self, path: Path | None) -> None:
        """Make the user's folders file (Music.juke) visible to every query as schema ``mj``."""
        self._folders_file = Path(path) if path else None
        self.close_thread_connection()
        self.connect()

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Bring databases created by older versions up to the current schema."""
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tracks)")}
        if "folder" not in columns:
            conn.execute("ALTER TABLE tracks ADD COLUMN folder TEXT NOT NULL DEFAULT ''")
        station_columns = {row[1] for row in conn.execute("PRAGMA table_info(stations)")}
        if station_columns and "source_url" not in station_columns:
            conn.execute("ALTER TABLE stations ADD COLUMN source_url TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_folder ON tracks (folder COLLATE NOCASE)")
        conn.commit()

    # -- connection handling -------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA foreign_keys=ON")  # songs removed from the library leave their playlists
            if self._folders_file is not None:
                conn.execute("ATTACH DATABASE ? AS mj", (str(self._folders_file),))
                conn.execute("PRAGMA mj.journal_mode=DELETE")      # Music.juke stays a single file
            self._local.conn = conn
        return conn

    def close_thread_connection(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -- writing ---------------------------------------------------------------
    def upsert_many(self, rows: Iterable[dict]) -> None:
        """Insert or refresh tracks; favourites and play statistics survive."""
        now = time.time()
        params = []
        for row in rows:
            row = dict(row)
            row.setdefault("year", 0)
            row.setdefault("track_no", 0)
            row.setdefault("duration", 0.0)
            row.setdefault("bitrate", 0)
            row.setdefault("cover_key", "")
            row.setdefault("mtime", 0.0)
            row.setdefault("size", 0)
            row.setdefault("folder", "")
            row["search_text"] = search_text_for(row["title"], row["artist"], row["album"], row["genre"])
            params.append(tuple(row[f] for f in _UPSERT_FIELDS) + (now,))
        if not params:
            return
        assignments = ", ".join(f"{f}=excluded.{f}" for f in _UPSERT_FIELDS[2:])
        placeholders = ", ".join("?" * (len(_UPSERT_FIELDS) + 1))
        sql = (
            f"INSERT INTO tracks ({', '.join(_UPSERT_FIELDS)}, added_at) VALUES ({placeholders}) "
            f"ON CONFLICT(source_type, location) DO UPDATE SET {assignments}"
        )
        conn = self.connect()
        with conn:
            conn.executemany(sql, params)

    def delete_local_under(self, directories: Iterable[str]) -> int:
        """Take every local song below these directories out of the library (the files stay on the disk)."""
        conn = self.connect()
        removed = 0
        with conn:
            for directory in directories:
                prefix = directory.rstrip(os.sep) + os.sep
                removed += conn.execute("DELETE FROM tracks WHERE source_type=? AND substr(location, 1, ?)=?",
                                        (SOURCE_LOCAL, len(prefix), prefix)).rowcount
        return removed

    def delete_locations(self, source_type: str, locations: Iterable[str]) -> int:
        conn = self.connect()
        removed = 0
        batch = list(locations)
        with conn:
            for start in range(0, len(batch), 500):
                chunk = batch[start:start + 500]
                marks = ",".join("?" * len(chunk))
                removed += conn.execute(
                    f"DELETE FROM tracks WHERE source_type=? AND location IN ({marks})",
                    (source_type, *chunk),
                ).rowcount
        return removed

    def replace_source(self, source_type: str, rows: list[dict]) -> None:
        """Make the stored tracks of one source match ``rows`` exactly."""
        keep = {r["location"] for r in rows}
        stale = [loc for loc in self.locations(source_type) if loc not in keep]
        self.upsert_many(rows)
        self.delete_locations(source_type, stale)

    def apply_sync(self, source_type: str, rows: list[dict], complete: bool) -> None:
        """Store a sync result. An incomplete one only adds/updates: songs it did not reach are kept."""
        if complete:
            self.replace_source(source_type, rows)
        else:
            self.upsert_many(rows)

    def update_tags(self, track_id: int, **fields) -> None:
        allowed = {"title", "artist", "album", "genre", "year", "track_no", "cover_key"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if not fields:
            return
        conn = self.connect()
        with conn:
            conn.execute(
                f"UPDATE tracks SET {', '.join(k + '=?' for k in fields)} WHERE id=?",
                (*fields.values(), track_id),
            )
            row = conn.execute("SELECT title, artist, album, genre FROM tracks WHERE id=?", (track_id,)).fetchone()
            if row:
                conn.execute("UPDATE tracks SET search_text=? WHERE id=?", (search_text_for(*row), track_id))

    def set_favorite(self, ids: Sequence[int], value: bool) -> None:
        conn = self.connect()
        with conn:
            conn.executemany("UPDATE tracks SET favorite=? WHERE id=?", [(int(value), i) for i in ids])

    def record_start(self, track_id: int) -> None:
        conn = self.connect()
        with conn:
            conn.execute("UPDATE tracks SET last_played=? WHERE id=?", (time.time(), track_id))

    def record_completed(self, track_id: int) -> None:
        conn = self.connect()
        with conn:
            conn.execute("UPDATE tracks SET play_count = play_count + 1 WHERE id=?", (track_id,))

    # -- reading ---------------------------------------------------------------
    def locations(self, source_type: str) -> list[str]:
        cur = self.connect().execute("SELECT location FROM tracks WHERE source_type=?", (source_type,))
        return [r[0] for r in cur]

    def local_index(self) -> dict[str, tuple[float, int]]:
        cur = self.connect().execute("SELECT location, mtime, size FROM tracks WHERE source_type=?", (SOURCE_LOCAL,))
        return {loc: (mtime, size) for loc, mtime, size in cur}

    def count(self, source_type: str | None = None) -> int:
        if source_type:
            row = self.connect().execute("SELECT COUNT(*) FROM tracks WHERE source_type=?", (source_type,)).fetchone()
        else:
            row = self.connect().execute("SELECT COUNT(*) FROM tracks").fetchone()
        return row[0]

    def count_favorites(self) -> int:
        return self.connect().execute("SELECT COUNT(*) FROM tracks WHERE favorite=1").fetchone()[0]

    def get_track(self, track_id: int) -> Track | None:
        row = self.connect().execute(f"SELECT {_COLUMNS} FROM tracks WHERE id=?", (track_id,)).fetchone()
        return Track.from_row(row) if row else None

    def find_by_location(self, source_type: str, location: str) -> Track | None:
        row = self.connect().execute(
            f"SELECT {_COLUMNS} FROM tracks WHERE source_type=? AND location=?", (source_type, location)
        ).fetchone()
        return Track.from_row(row) if row else None

    def tracks_by_ids(self, ids: Sequence[int]) -> list[Track]:
        """Rows for ``ids`` in the same order (ids that no longer exist are dropped)."""
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        cur = self.connect().execute(f"SELECT {_COLUMNS} FROM tracks WHERE id IN ({marks})", tuple(ids))
        by_id = {row[0]: Track.from_row(row) for row in cur}
        return [by_id[i] for i in ids if i in by_id]

    def _where(self, scope: Scope, text: str) -> tuple[str, list]:
        clauses: list[str] = []
        args: list = []
        if scope.source_type:
            clauses.append("source_type = ?")
            args.append(scope.source_type)
        if scope.artist is not None:
            clauses.append("artist = ? COLLATE NOCASE")
            args.append(scope.artist)
        if scope.album is not None:
            clauses.append("album = ? COLLATE NOCASE")
            args.append(scope.album)
        if scope.genre is not None:
            clauses.append("genre = ? COLLATE NOCASE")
            args.append(scope.genre)
        if scope.folder is not None:
            like = scope.folder.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
            clauses.append("(folder = ? COLLATE NOCASE OR folder LIKE ? ESCAPE '\\')")
            args.extend([scope.folder, like])
        if scope.ufolders is not None:
            if self._folders_file is None or not scope.ufolders:
                clauses.append("0")
            else:
                marks = ",".join("?" * len(scope.ufolders))
                clauses.append(f"(source_type = 'local' AND location IN (SELECT path FROM mj.folder_items WHERE folder_id IN ({marks})))")
                args.extend(scope.ufolders)
        if scope.duplicates:
            key = "lower(title), lower(artist), lower(album)"
            if scope.duplicates == "exact":
                key += ", CAST(ROUND(duration) AS INTEGER), size"
            clauses.append(f"title != '' AND ({key}) IN (SELECT {key} FROM tracks WHERE title != '' GROUP BY {key} HAVING COUNT(*) > 1)")
        if scope.favorites:
            clauses.append("favorite = 1")
        if scope.recent:
            clauses.append("last_played > 0")
        for token in normalize(text).split():
            clauses.append("instr(search_text, ?) > 0")
            args.append(token)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", args

    def query_ids(self, scope: Scope = Scope(), text: str = "", sort: str | None = None,
                  descending: bool = False, limit: int | None = None) -> list[int]:
        """Ordered ids for a view. ``sort`` is a key of SORT_EXPRESSIONS or None (natural order)."""
        where, args = self._where(scope, text)
        if scope.duplicates and sort is None:
            # the copies of a song sit together, the best-sounding one first
            order = "lower(title), lower(artist), lower(album), bitrate DESC, size DESC, id"
        elif scope.recent and sort is None:
            order = "last_played DESC"
        elif scope.folder is not None and sort is None:
            order = "folder COLLATE NOCASE, track_no, title COLLATE NOCASE"
        elif sort in SORT_EXPRESSIONS:
            order = SORT_EXPRESSIONS[sort] + (" DESC" if descending else "")
            order += ", " + NATURAL_ORDER
        else:
            order = NATURAL_ORDER
        sql = f"SELECT id FROM tracks{where} ORDER BY {order}, id"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [r[0] for r in self.connect().execute(sql, args)]

    def summary(self, scope: Scope = Scope(), text: str = "") -> tuple[int, float]:
        where, args = self._where(scope, text)
        row = self.connect().execute(f"SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM tracks{where}", args).fetchone()
        return row[0], row[1]

    # -- radio stations ----------------------------------------------------------------------
    _STATION_COLS = "id, name, stream_url, homepage, favicon, tags, country, codec, bitrate, uuid, source_url"

    def stations(self) -> list[Station]:
        cur = self.connect().execute(f"SELECT {self._STATION_COLS} FROM stations ORDER BY name COLLATE NOCASE")
        return [Station(*row) for row in cur]

    def add_station(self, station: Station) -> int:
        """Save (or refresh, matched by stream address) a station and return its id."""
        conn = self.connect()
        with conn:
            conn.execute(
                "INSERT INTO stations (name, stream_url, homepage, favicon, tags, country, codec, bitrate, uuid, source_url, added_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(stream_url) DO UPDATE SET name=excluded.name, "
                "homepage=excluded.homepage, favicon=excluded.favicon, tags=excluded.tags, country=excluded.country, "
                "codec=excluded.codec, bitrate=excluded.bitrate, uuid=excluded.uuid, "
                "source_url=CASE WHEN excluded.source_url != '' THEN excluded.source_url ELSE stations.source_url END",
                (station.name.strip(), station.stream_url, station.homepage, station.favicon, station.tags,
                 station.country, station.codec, station.bitrate, station.uuid, station.source_url, time.time()))
            return conn.execute("SELECT id FROM stations WHERE stream_url=?", (station.stream_url,)).fetchone()[0]

    def update_station_stream(self, station_id: int, stream_url: str, codec: str = "", bitrate: int = 0, favicon: str = "") -> bool:
        """The station moved to a new stream address. False if another saved station already uses it."""
        conn = self.connect()
        try:
            with conn:
                conn.execute("UPDATE stations SET stream_url=?, codec=CASE WHEN ?!='' THEN ? ELSE codec END, "
                             "bitrate=CASE WHEN ?>0 THEN ? ELSE bitrate END, favicon=CASE WHEN ?!='' THEN ? ELSE favicon END WHERE id=?",
                             (stream_url, codec, codec, bitrate, bitrate, favicon, favicon, station_id))
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_station(self, station_id: int) -> None:
        conn = self.connect()
        with conn:
            conn.execute("DELETE FROM stations WHERE id=?", (station_id,))

    def station_urls(self) -> set[str]:
        return {r[0] for r in self.connect().execute("SELECT stream_url FROM stations")}

    def count_stations(self) -> int:
        return self.connect().execute("SELECT COUNT(*) FROM stations").fetchone()[0]

    # -- playlists ------------------------------------------------------------------------
    def playlists(self) -> list[tuple[int, str, int]]:
        """(id, name, song count), alphabetically."""
        cur = self.connect().execute(
            "SELECT p.id, p.name, COUNT(t.track_id) FROM playlists p "
            "LEFT JOIN playlist_tracks t ON t.playlist_id = p.id GROUP BY p.id ORDER BY p.name COLLATE NOCASE")
        return [(r[0], r[1], r[2]) for r in cur]

    def create_playlist(self, name: str) -> int:
        conn = self.connect()
        with conn:
            return conn.execute("INSERT INTO playlists (name, created_at) VALUES (?, ?)", (name.strip(), time.time())).lastrowid

    def rename_playlist(self, playlist_id: int, name: str) -> None:
        conn = self.connect()
        with conn:
            conn.execute("UPDATE playlists SET name=? WHERE id=?", (name.strip(), playlist_id))

    def delete_playlist(self, playlist_id: int) -> None:
        conn = self.connect()
        with conn:
            conn.execute("DELETE FROM playlists WHERE id=?", (playlist_id,))

    def playlist_track_ids(self, playlist_id: int) -> list[int]:
        cur = self.connect().execute(
            "SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY position", (playlist_id,))
        return [r[0] for r in cur]

    def add_to_playlist(self, playlist_id: int, track_ids: Sequence[int]) -> None:
        conn = self.connect()
        with conn:
            start = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_tracks WHERE playlist_id=?", (playlist_id,)).fetchone()[0]
            conn.executemany("INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
                             [(playlist_id, tid, start + i) for i, tid in enumerate(track_ids)])

    def remove_from_playlist(self, playlist_id: int, track_ids: Sequence[int]) -> None:
        conn = self.connect()
        with conn:
            conn.executemany("DELETE FROM playlist_tracks WHERE playlist_id=? AND track_id=?",
                             [(playlist_id, tid) for tid in track_ids])

    def folders(self, source_type: str) -> list[str]:
        """Every distinct folder path of a source ("Artist/Album", ...)."""
        cur = self.connect().execute(
            "SELECT DISTINCT folder FROM tracks WHERE source_type=? AND folder != ''", (source_type,))
        return [r[0] for r in cur]

    def distinct(self, field: str) -> list[tuple[str, int]]:
        """(value, track count) for artist / album / genre, case-insensitively grouped."""
        if field not in ("artist", "album", "genre"):
            raise ValueError(field)
        cur = self.connect().execute(
            f"SELECT {field}, COUNT(*) FROM tracks GROUP BY {field} COLLATE NOCASE "
            f"ORDER BY ({field} = '') , {field} COLLATE NOCASE"
        )
        return [(r[0], r[1]) for r in cur]
