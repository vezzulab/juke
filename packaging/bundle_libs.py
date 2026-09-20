#!/usr/bin/env python3
"""Copy libVLC, the audio-relevant VLC plugins and their shared-library dependencies into an AppDir.

    bundle_libs.py APPDIR

Libraries every desktop already provides (glibc, GL, X11/xcb, fontconfig, the sound server client
libraries, libstdc++...) are deliberately left out: bundling those breaks newer systems.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_DIRS = ("access", "audio_filter", "audio_mixer", "audio_output", "codec", "demux", "misc",
               "packetizer", "stream_filter", "stream_extractor", "keystore")
SKIP_PLUGINS = ("libaout_pipewire_plugin.so",)  # libVLC 3's PipeWire output crashes on early volume changes

HOST_LIBS = re.compile(
    r"^(ld-linux.*|linux-vdso|libc|libm|libdl|libpthread|librt|libutil|libresolv|libnsl|libanl|libcrypt|"
    r"libBrokenLocale|libnss_.*|libthread_db|libGL|libGLX|libGLdispatch|libEGL|libOpenGL|libGLESv[12]|libdrm.*|"
    r"libgbm|libX11|libX11-xcb|libXau|libXdmcp|libXext|libXrender|libXi|libXfixes|libXcursor|libXrandr|"
    r"libXinerama|libXv|libXxf86vm|libXcomposite|libXdamage|libxcb.*|libxkbcommon.*|libfontconfig|libfreetype|"
    r"libharfbuzz.*|libglib-2\.0|libgobject-2\.0|libgmodule-2\.0|libgio-2\.0|libgthread-2\.0|libdbus-1|"
    r"libsystemd|libudev|libasound|libwayland-.*|libselinux|libstdc\+\+|libgcc_s|libpulse.*|libjack.*|"
    r"libsndio|libmount|libblkid|libcap|libva.*|libvdpau|libSM|libICE)\.so.*$"
)


def find_plugin_root() -> Path:
    candidates = [os.environ.get("VLC_PLUGIN_PATH", "")]
    candidates += glob.glob("/usr/lib*/vlc/plugins") + glob.glob("/usr/lib/*-linux-gnu/vlc/plugins")
    for candidate in candidates:
        if candidate and (Path(candidate) / "audio_output").is_dir():
            return Path(candidate)
    sys.exit("VLC plugins not found (install vlc / vlc-libs)")


def find_lib(name: str) -> Path:
    out = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(name + " ") and ("x86-64" in line or "AArch64" in line):
            return Path(line.split("=>")[1].strip())
    sys.exit(f"{name} not found (install libvlc)")


def dependencies(path: Path) -> list[Path]:
    out = subprocess.run(["ldd", str(path)], capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines():
        match = re.search(r"=>\s+(/\S+)", line)
        if match:
            found.append(Path(match.group(1)))
    return found


def main(appdir: Path) -> None:
    lib_dir = appdir / "usr/lib"
    plugin_dest = lib_dir / "vlc/plugins"
    plugin_dest.mkdir(parents=True, exist_ok=True)
    roots: list[Path] = []
    for soname in ("libvlc.so.5", "libvlccore.so.9"):
        real = find_lib(soname).resolve()
        shutil.copy2(real, lib_dir / soname)
        roots.append(lib_dir / soname)

    source = find_plugin_root()
    for name in PLUGIN_DIRS:
        for plugin in (source / name).glob("*.so"):
            if plugin.name in SKIP_PLUGINS:
                continue
            target = plugin_dest / name
            target.mkdir(exist_ok=True)
            shutil.copy2(plugin, target / plugin.name)
            roots.append(target / plugin.name)

    queue, seen = list(roots), set()
    copied = 0
    while queue:
        current = queue.pop()
        for dep in dependencies(current):
            real = dep.resolve()
            soname = dep.name
            stem = soname
            if HOST_LIBS.match(stem) or soname in seen:
                continue
            seen.add(soname)
            target = lib_dir / soname
            if not target.exists():
                shutil.copy2(real, target)
                copied += 1
            queue.append(target)
    print(f"bundled libvlc + {sum(1 for _ in plugin_dest.rglob('*.so'))} plugins + {copied} dependency libraries")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
