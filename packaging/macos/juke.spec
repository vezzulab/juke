# PyInstaller recipe for Juke.app (Apple Silicon).  Run through packaging/build-macos.sh, which sets the environment.
#
#   JUKE_VLC_RUNTIME   folder made by prepare_vlc.py (lib/ and plugins/), bundled as <app>/vlc
#   JUKE_ICNS          the app icon
import os
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).resolve().parents[1]
vlc_runtime = Path(os.environ["JUKE_VLC_RUNTIME"])
icns = os.environ["JUKE_ICNS"]
version = re.search(r'__version__ = "(.*)"', (root / "juke" / "__init__.py").read_text()).group(1)

# Qt parts Juke never touches: leaving them out saves the better part of 100 MB
unused_qt = ["QtQml", "QtQuick", "QtQuickWidgets", "QtQuickControls2", "QtPdf", "QtPdfWidgets", "QtDesigner", "Qt3DCore",
             "QtWebEngineCore", "QtWebEngineWidgets", "QtWebChannel", "QtMultimedia", "QtMultimediaWidgets", "QtCharts",
             "QtDataVisualization", "QtGraphs", "QtLocation", "QtSensors", "QtSerialPort", "QtNfc", "QtBluetooth",
             "QtTest", "QtHelp", "QtOpenGL", "QtOpenGLWidgets", "QtPrintSupport", "QtSql", "QtXml", "QtTextToSpeech",
             "QtPositioning", "QtRemoteObjects", "QtScxml", "QtStateMachine", "QtSpatialAudio", "QtNetworkAuth"]

a = Analysis(
    [str(root / "packaging" / "macos" / "entry.py")],
    pathex=[str(root)],
    datas=[(str(root / "juke" / "assets"), "juke/assets"), (str(vlc_runtime), "vlc")],
    hiddenimports=collect_submodules("juke") + collect_submodules("yt_dlp") + ["MediaPlayer", "vlc"],
    excludes=[f"PySide6.{name}" for name in unused_qt] + ["tkinter", "unittest", "pydoc_data", "test"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Juke", console=False, argv_emulation=False,
          target_arch="arm64", codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Juke")
app = BUNDLE(
    coll,
    name="Juke.app",
    icon=icns,
    bundle_identifier="io.github.vezzulab.juke",
    version=version,
    info_plist={
        "CFBundleName": "Juke",
        "CFBundleDisplayName": "Juke",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "JukeBuild": os.environ.get("JUKE_BUILD", ""),        # which build of this version: a rebuilt one is offered as an update
        "LSMinimumSystemVersion": "15.0",     # what the bundled Python and Qt were built for
        "LSApplicationCategoryType": "public.app-category.music",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Juke by Vezzu Studio",
        "NSRequiresAquaSystemAppearance": False,      # follows the system's light / dark appearance
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "Audio",
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Alternate",
            "LSItemContentTypes": ["public.audio", "public.mp3", "org.xiph.flac", "public.mpeg-4-audio", "com.microsoft.waveform-audio",
                                   "public.aiff-audio", "org.xiph.ogg-audio"],
        }],
    },
)
