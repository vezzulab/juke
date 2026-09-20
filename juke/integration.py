"""Applications-menu integration (Linux desktop entry + icons).

An AppImage is a single file, so nothing shows up in the start menu by itself.
With the user's consent Juke writes a .desktop entry and its icon into the
user's XDG directories, pointing at wherever the AppImage currently lives.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import APP_ID, __version__
from .assets import ICON_SVG

ICON_SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)
MIME_TYPES = (
    "audio/mpeg", "audio/flac", "audio/x-flac", "audio/ogg", "audio/x-vorbis+ogg", "audio/opus",
    "audio/mp4", "audio/x-m4a", "audio/aac", "audio/wav", "audio/x-wav", "audio/x-ms-wma",
    "audio/x-aiff", "audio/x-ape", "audio/x-wavpack", "audio/x-musepack",
)


def _data_home() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    return Path(base) if base and os.path.isabs(base) else Path.home() / ".local" / "share"


def desktop_file() -> Path:
    return _data_home() / "applications" / f"{APP_ID}.desktop"


def _icon_root() -> Path:
    return _data_home() / "icons" / "hicolor"


def appimage_path() -> Path | None:
    """Path of the running AppImage (the runtime exports $APPIMAGE), if any."""
    value = os.environ.get("APPIMAGE")
    return Path(value) if value and Path(value).is_file() else None


def launch_command() -> str:
    """What the menu entry runs: the AppImage itself, or ``python -m juke`` from source."""
    image = appimage_path()
    return _quote(str(image)) if image else f"{_quote(sys.executable)} -m juke"


def _quote(arg: str) -> str:
    """Quote for the Exec key of a desktop entry."""
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def entry_text() -> str:
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.5",
        "Name=Juke",
        "GenericName=Music Player",
        "GenericName[es]=Reproductor de música",
        "Comment=A modern music player with a 10-band equalizer and Airsonic streaming",
        "Comment[es]=Un reproductor de música moderno con ecualizador de 10 bandas y streaming Airsonic",
        f"Exec={launch_command()} %U",
        f"Icon={APP_ID}",
        "Terminal=false",
        "Categories=AudioVideo;Audio;Player;Music;Qt;",
        f"MimeType={';'.join(MIME_TYPES)};",
        "Keywords=music;audio;player;equalizer;airsonic;subsonic;flac;mp3;",
        "Keywords[es]=música;audio;reproductor;ecualizador;airsonic;subsonic;flac;mp3;",
        f"StartupWMClass={APP_ID}",
        "StartupNotify=false",
        f"X-Juke-Version={__version__}",
        "",
    ])


def is_installed() -> bool:
    return desktop_file().is_file()


def needs_refresh() -> bool:
    """Installed entry no longer matches where/what we are running from."""
    try:
        return desktop_file().read_text(encoding="utf-8") != entry_text()
    except OSError:
        return False


def install() -> None:
    """Write the .desktop entry and every icon size (rendered from the bundled SVG)."""
    from PySide6.QtCore import QStandardPaths  # noqa: F401 - ensures Qt core is initialised
    from .gui.icons import render_svg

    svg = ICON_SVG.read_bytes()
    scalable = _icon_root() / "scalable" / "apps"
    scalable.mkdir(parents=True, exist_ok=True)
    (scalable / f"{APP_ID}.svg").write_bytes(svg)
    for size in ICON_SIZES:
        target = _icon_root() / f"{size}x{size}" / "apps"
        target.mkdir(parents=True, exist_ok=True)
        render_svg(svg, size, dpr=1.0).save(str(target / f"{APP_ID}.png"), "PNG")
    entry = desktop_file()
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(entry_text(), encoding="utf-8")
    entry.chmod(0o755)
    _refresh_caches()


def uninstall() -> None:
    paths = [desktop_file(), _icon_root() / "scalable" / "apps" / f"{APP_ID}.svg"]
    paths += [_icon_root() / f"{s}x{s}" / "apps" / f"{APP_ID}.png" for s in ICON_SIZES]
    for path in paths:
        try:
            path.unlink()
        except OSError:
            pass
    _refresh_caches()


def _refresh_caches() -> None:
    """Best effort: tell the desktop about the new entry/icons (tools may be absent)."""
    commands = (
        ["update-desktop-database", str(desktop_file().parent)],
        ["gtk-update-icon-cache", "-q", "-f", "-t", str(_icon_root())],
    )
    for command in commands:
        try:
            subprocess.run(command, capture_output=True, timeout=8, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
