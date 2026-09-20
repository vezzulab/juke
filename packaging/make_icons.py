"""Render the SVG icon into the hicolor PNG sizes used inside the AppDir.

    QT_QPA_PLATFORM=offscreen python make_icons.py APPDIR
"""

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

app = QGuiApplication([])
from juke.assets import ICON_SVG  # noqa: E402
from juke.gui.icons import render_svg  # noqa: E402

appdir = Path(sys.argv[1])
svg = ICON_SVG.read_bytes()
scalable = appdir / "usr/share/icons/hicolor/scalable/apps"
scalable.mkdir(parents=True, exist_ok=True)
(scalable / "juke.svg").write_bytes(svg)
for size in (16, 22, 24, 32, 48, 64, 128, 256, 512):
    target = appdir / f"usr/share/icons/hicolor/{size}x{size}/apps"
    target.mkdir(parents=True, exist_ok=True)
    render_svg(svg, size, 1.0).save(str(target / "juke.png"), "PNG")
render_svg(svg, 256, 1.0).save(str(appdir / "juke.png"), "PNG")   # top-level icon + .DirIcon source
print("icons written to", appdir)
