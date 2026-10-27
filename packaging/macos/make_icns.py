"""Render the SVG icon into a macOS .icns file, with the margin around the artwork that macOS icons have.

    QT_QPA_PLATFORM=offscreen python make_icns.py OUT.icns
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtGui import QGuiApplication

app = QGuiApplication([])
from juke.gui.icons import mac_pixmap  # noqa: E402

out = Path(sys.argv[1])
work = Path(tempfile.mkdtemp(prefix="juke-icns-")) / "Juke.iconset"
work.mkdir()
for size in (16, 32, 128, 256, 512):
    mac_pixmap(size).save(str(work / f"icon_{size}x{size}.png"), "PNG")          # with the margin macOS icons have
    mac_pixmap(size * 2).save(str(work / f"icon_{size}x{size}@2x.png"), "PNG")
subprocess.run(["iconutil", "-c", "icns", "-o", str(out), str(work)], check=True)
shutil.rmtree(work.parent)
print("icon written to", out)
