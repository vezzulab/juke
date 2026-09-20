"""Application entry point."""

from __future__ import annotations

import argparse
import os
import signal
import sys

from . import APP_ID, APP_NAME, __version__


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="juke", description="A modern 3-pane music player for Linux.")
    parser.add_argument("files", nargs="*", help="audio files or file:// URLs to play")
    parser.add_argument("--version", action="version", version=f"Juke {__version__}")
    parser.add_argument("--install-desktop", action="store_true", help="add Juke to the applications menu and exit")
    parser.add_argument("--uninstall-desktop", action="store_true", help="remove Juke from the applications menu and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)

    # Wayland first, X11 as fallback; must be decided before Qt starts.
    if os.environ.get("WAYLAND_DISPLAY") and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

    from PySide6.QtCore import Qt, QTimer
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

    from . import integration
    from .assets import FONTS_DIR
    from .audio.engine import AudioEngine
    from .audio.equalizer import Equalizer
    from .config import CONFIG_PATH, DB_PATH, Config, ensure_dirs
    from .db.database import Database
    from .gui import icons, styles
    from .gui.main_window import MainWindow
    from .i18n import translator

    if args.install_desktop or args.uninstall_desktop:
        integration.install() if args.install_desktop else integration.uninstall()
        return 0

    for font in sorted(FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(font))
    app.setStyle("Fusion")  # one predictable base for the stylesheet on every desktop
    app.setPalette(styles.build_palette())
    app.setStyleSheet(styles.build_stylesheet())
    app.setWindowIcon(icons.app_icon())

    ensure_dirs()
    config = Config(CONFIG_PATH)
    translator.set_language(config.get("language"))
    db = Database(DB_PATH)
    engine = AudioEngine()
    equalizer = Equalizer(config)
    window = MainWindow(config, db, engine, equalizer)
    window.show()
    if args.files:
        QTimer.singleShot(600, lambda: window.open_paths(args.files))

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    pump = QTimer()  # lets Python deliver Ctrl+C while Qt's loop runs
    pump.start(500)
    pump.timeout.connect(lambda: None)
    return app.exec()
