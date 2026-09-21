"""Global configuration: XDG paths, defaults and JSON persistence."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from . import APP_ID


def _xdg(env: str, fallback: str) -> Path:
    base = os.environ.get(env)
    root = Path(base) if base and os.path.isabs(base) else Path.home() / fallback
    return root / APP_ID


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config")
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share")
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache")
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
    "muted": False,
    "shuffle": False,
    "repeat": "off",  # off | all | one
    "equalizer": {"enabled": False, "preamp": 0.0, "gains": [0.0] * 10, "preset": "Flat"},
    "custom_presets": {},  # name -> {"preamp": float, "gains": [10 floats]}
    "airsonic": {"enabled": False, "url": "", "username": "", "password": "", "auth": "auto"},  # auth: auto | token | password
    "window": {"geometry": "", "splitter": [240, 960]},
    "desktop_integration": {"asked": False, "enabled": False},
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
