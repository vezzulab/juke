"""Global configuration: XDG paths (Library folders on a Mac), defaults and JSON persistence."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from . import APP_ID
from .system import IS_MAC


def _xdg(env: str, fallback: str) -> Path:
    base = os.environ.get(env)
    root = Path(base) if base and os.path.isabs(base) else Path.home() / fallback
    return root / APP_ID


def locations(mac: bool = IS_MAC) -> tuple[Path, Path, Path]:
    """Where settings, the library and the caches live: XDG folders, or the Library folders where a Mac keeps them
    (an XDG variable somebody set is honoured on both)."""
    if mac:
        return (_xdg("XDG_CONFIG_HOME", "Library/Application Support"), _xdg("XDG_DATA_HOME", "Library/Application Support"),
                _xdg("XDG_CACHE_HOME", "Library/Caches"))
    return _xdg("XDG_CONFIG_HOME", ".config"), _xdg("XDG_DATA_HOME", ".local/share"), _xdg("XDG_CACHE_HOME", ".cache")


CONFIG_DIR, DATA_DIR, CACHE_DIR = locations()
COVERS_DIR = CACHE_DIR / "covers"
DB_PATH = DATA_DIR / "library.db"
CONFIG_PATH = CONFIG_DIR / "settings.json"

AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".m4b", ".aac", ".wav",
     ".wma", ".ape", ".wv", ".mpc", ".aif", ".aiff"}
)

DEFAULTS: dict[str, Any] = {
    "language": "auto",  # auto | en | es
    "music_dirs": [str(Path.home() / "Music")],
    "scan_on_start": True,
    "lyrics": {"auto_search": False},   # ask LRCLIB for songs that have no lyrics, by themselves (off: only when asked)
    "theme": "auto",  # auto (follow the desktop) | dark | light
    "meter": "auto",  # level-meter animation: auto (mains power only) | on | off
    "volume": 80,
    "stay_awake": True,   # ask the desktop not to sleep or blank the screen while music plays
    "volume_follows_system": True,   # the slider is the computer's volume (keys, panel and mixer move it together with Juke)
    "crossfade_last": 5,   # the overlap the light under the volume turns back on with
    "crossfade": 0,   # seconds the next song comes in before the current one ends; 0 = off
    "muted": False,
    "shuffle": False,
    "repeat": "off",  # off | all | one
    "whats_new": "",  # the last version whose "what is new" window was shown, so it comes up once
    "queue": [],  # ids of the songs lined up in the queue; written at every change so a crash does not lose them
    "equalizer": {"enabled": False, "preamp": 0.0, "gains": [0.0] * 10, "preset": "Flat"},
    "custom_presets": {},  # name -> {"preamp": float, "gains": [10 floats]}
    "airsonic": {"enabled": False, "url": "", "username": "", "password": "", "auth": "auto"},  # auth: auto | token | password
    "window": {"geometry": "", "splitter": [240, 960]},
    "desktop_integration": {"asked": False, "enabled": False},
    "sync": {"server": "https://juke-sync.vezzulab.workers.dev", "code": "", "updated": 0, "auto": True, "settings_at": 0,
             "settings_hash": "", "last_ok": 0.0, "last_error": ""},   # the sync server (cloudflare/sync), this person's code and the copy last seen there
    "update": {"enabled": True, "last_check": 0.0, "skipped": "", "snoozed": "", "snooze_until": 0.0},
}


def ensure_dirs() -> None:
    for directory in (CONFIG_DIR, DATA_DIR, CACHE_DIR, COVERS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _merge(defaults: Any, loaded: Any) -> Any:
    """Overlay ``loaded`` on ``defaults`` keeping the default's shape for dicts."""
    if isinstance(defaults, dict) and isinstance(loaded, dict):
        merged = copy.deepcopy(defaults)
        for key, value in loaded.items():
            merged[key] = _merge(defaults[key], value) if key in defaults else value
        return merged
    if isinstance(defaults, list) and isinstance(loaded, list) and defaults and not isinstance(defaults[0], str):
        return loaded if len(loaded) == len(defaults) else copy.deepcopy(defaults)
    return loaded if type(loaded) is type(defaults) or defaults is None else copy.deepcopy(defaults)


class Config:
    """Small dotted-key JSON store (``cfg.get("airsonic.url")``)."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(loaded, dict):
            self.data = _merge(DEFAULTS, loaded)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def save(self) -> None:
        """Atomic write, readable only by the owner (the file can hold a password)."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".settings-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(self.data, fh, indent=2, ensure_ascii=False)
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path)
            except OSError:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
