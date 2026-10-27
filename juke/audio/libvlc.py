"""Where libVLC lives on a Mac, so ``import vlc`` finds it."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


def home() -> Path | None:
    """The folder with ``lib/libvlc.dylib`` and ``plugins/``: the one inside Juke.app, else an installed VLC."""
    candidates = [os.environ.get("JUKE_VLC_DIR", "")]
    frozen = getattr(sys, "_MEIPASS", "")
    if frozen:
        candidates.append(str(Path(frozen) / "vlc"))
    candidates += ["/Applications/VLC.app/Contents/MacOS", str(Path.home() / "Applications/VLC.app/Contents/MacOS")]
    for candidate in candidates:
        if candidate and (Path(candidate) / "lib" / "libvlc.dylib").is_file() and (Path(candidate) / "plugins").is_dir():
            return Path(candidate)
    return None


def prepare() -> None:
    """python-vlc only looks in /Applications/VLC.app. Juke carries its own libVLC, so load that one first (libvlccore
    before libvlc: the second names the first through @rpath) and tell python-vlc and libVLC where everything is."""
    found = home()
    if found is None:
        return
    ctypes.CDLL(str(found / "lib" / "libvlccore.dylib"))
    os.environ["PYTHON_VLC_LIB_PATH"] = str(found / "lib" / "libvlc.dylib")
    os.environ["VLC_PLUGIN_PATH"] = str(found / "plugins")
