#!/usr/bin/env python3
"""Copy libVLC and the plugins an audio player needs out of a VLC.app, into OUT/{lib,plugins}.

    prepare_vlc.py /path/to/VLC.app OUT

Everything that draws video, serves or records streams, or belongs to VLC's own interface is left out: Juke plays sound.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

LEFT_OUT = re.compile(
    r"^lib(?:"
    # video output, filters, converters, decoders and overlays
    r"vout_.*|caopengllayer|glconv_.*|ci_filters|cvpx|videotoolbox|x26[45]|x26410b|vpx|dav1d|aom|theora|kate|libass|freetype|"
    r"zvbi|telx|dvbsub|cvdsub|svcdsub|vobsub|spudec|subsdec|subsdelay|substx3g|subsusf|textst|ttml|webvtt|aribsub|cc|t140|"
    r"anaglyph|alphamask|antiflicker|ball|blend.*|bluescreen|canvas|colorthres|croppadd|deinterlace|edgedetection|erase|"
    r"extract|fps|freeze|gaussianblur|gestures|goom|gradfun|gradient|grain|grey_yuv|hqdn3d|i4.*|invert|logo|magnify|marq|"
    r"mirror|mosaic|motion.*|oldmovie|posterize|postproc|psychedelic|puzzle|remoteosd|ripple|rotate|scale|scene|sepia|"
    r"sharpen|transform|vhs|wall|yuv.*|yuy2_.*|rv32|swscale|image|dynamicoverlay|clone|mjpeg|"
    # things a player never does here
    r"stream_out_.*|mux_.*|access_output_.*|sap|bonjour|upnp|rist|srt|access_srt|shout|chromecast|osx_notifications|"
    r"libbluray|hotkeys|oldrc|netsync|console_logger|syslog|ncurses|lua|bluray.*|dvdnav|dvdread|cdda|vcd|screen|avcapture|"
    r"avaudiocapture|shm|vod_rtsp|rtpvideo|live555|nfs|sftp|macosx|mediadirs|addons.*|fingerprinter|export|record|"
    r"audiobargraph_.*|visual|audioscrobbler|gnutls_unused"
    r")_plugin\.dylib$"
)


def main(app: Path, out: Path) -> None:
    macos = app / "Contents" / "MacOS"
    if not (macos / "lib" / "libvlc.dylib").is_file():
        sys.exit(f"{app} is not a VLC.app")
    if out.exists():
        shutil.rmtree(out)
    (out / "lib").mkdir(parents=True)
    (out / "plugins").mkdir()
    for name in ("libvlc.dylib", "libvlc.5.dylib", "libvlccore.dylib", "libvlccore.9.dylib"):
        shutil.copy2(macos / "lib" / name, out / "lib" / name, follow_symlinks=False)
    kept = dropped = 0
    for plugin in sorted((macos / "plugins").iterdir()):
        if plugin.suffix != ".dylib" or LEFT_OUT.match(plugin.name):
            dropped += 1
            continue
        shutil.copy2(plugin, out / "plugins" / plugin.name)
        kept += 1
    print(f"libVLC: {kept} plugins kept, {dropped} left out")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
