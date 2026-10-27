"""Application entry point."""

from __future__ import annotations

import argparse
import os
import signal
import sys

from . import APP_ID, APP_NAME, __version__


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="juke", description="A modern 3-pane music player for Linux and macOS.")
    parser.add_argument("files", nargs="*", help="audio files or file:// URLs to play")
    parser.add_argument("--version", action="version", version=f"Juke {__version__}")
    parser.add_argument("--install-desktop", action="store_true", help="add Juke to the applications menu and exit")
    parser.add_argument("--uninstall-desktop", action="store_true", help="remove Juke from the applications menu and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)

    # Wayland first, X11 as fallback; must be decided before Qt starts.
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY") and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

    from PySide6.QtCore import QEvent, QObject, Qt, QTimer
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    from PySide6.QtWidgets import QApplication

    # HiDPI: Qt 6 scales automatically; pass fractional factors (125 %, 150 %...) through unrounded.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)  # matches juke.desktop so Wayland shows the right icon
    app.setQuitOnLastWindowClosed(True)

    opened: list[str] = []            # macOS hands "open with Juke" and drops on the Dock icon over events, not argv
    window = None

    class OpenEvents(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.FileOpen and event.file():
                if window is None:
                    opened.append(event.file())
                else:
                    window.open_paths([event.file()])
                return True
            return False

    open_events = OpenEvents(app)
    app.installEventFilter(open_events)

    from . import integration
    from .assets import FONTS_DIR
    from .audio.engine import AudioEngine
    from .audio.equalizer import Equalizer
    from .config import CONFIG_PATH, DATA_DIR, DB_PATH, Config, ensure_dirs
    from .db.database import Database
    from .db.folders import FolderStore, default_path
    from .gui import icons, styles
    from .gui.main_window import MainWindow
    from .gui.theme import ThemeManager
    from .i18n import translator

    if args.install_desktop or args.uninstall_desktop:
        if not integration.supported():
            print("The applications menu entry is a Linux thing; on a Mac, drag Juke.app to Applications.", file=sys.stderr)
            return 1
        integration.install() if args.install_desktop else integration.uninstall()
        return 0

    for font in sorted(FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(font))
    app.setStyle("Fusion")  # one predictable base for the stylesheet on every desktop
    app.setWindowIcon(icons.app_icon())

    ensure_dirs()
    from . import applog
    from .links import install_handlers

    install_handlers(app)             # links open with the desktop's environment, not the AppImage's

    applog.setup()                    # juke.log: what a person can read or send along with a problem
    applog.qt_messages()
    config = Config(CONFIG_PATH)
    theme = ThemeManager(app, config.get("theme"))
    theme.apply()                     # dark, light, or whatever the desktop is using
    translator.set_language(config.get("language"))
    db = Database(DB_PATH)
    folders = FolderStore(default_path(DATA_DIR))       # Music/Music.juke/folders.db
    engine = AudioEngine()
    equalizer = Equalizer(config)
    window = MainWindow(config, db, engine, equalizer, theme, folders)
    window.show()
    files = [*args.files, *opened]
    if files:
        QTimer.singleShot(600, lambda: window.open_paths(files))

    if sys.stdin is not None and sys.stdin.isatty():
        # Ctrl+C in a terminal: Python only sees signals while it runs, so give Qt's loop a slow
        # heartbeat. Launched from a menu (no terminal) there is no timer and no idle wake-up.
        signal.signal(signal.SIGINT, lambda *_: app.quit())
        pump = QTimer()
        pump.setTimerType(Qt.VeryCoarseTimer)
        pump.start(1000)
        pump.timeout.connect(lambda: None)
    return app.exec()
