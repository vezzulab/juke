"""Dark and light themes: one palette table each, rendered to a QSS stylesheet and a QPalette.

The colour names below (BASE, TEXT, ACCENT...) are module attributes that always hold the *current*
theme, so custom-painted widgets simply read ``styles.TEXT`` when they paint. Widgets that cache
colours (icons, brushes) listen to ``styles.signals.changed`` and rebuild them.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

DARK = {
    "BASE": "#1e1e2e",          # window background
    "MANTLE": "#181825",        # sidebar, top bar
    "PANEL": "#252538",         # cards, inputs, menus
    "SURFACE": "#2f2f45",       # hovers, buttons
    "OVERLAY": "#3a3a55",       # slider grooves, pressed
    "BORDER": "#2b2b40",
    "TEXT": "#cdd6f4",
    "SUBTEXT": "#9399b2",
    "MUTED": "#6c7086",
    "ACCENT": "#7aa2f7",
    "ACCENT2": "#cba6f7",
    "ACCENT_HOVER": "#8fb1f9",
    "ACCENT2_HOVER": "#d6b8fa",
    "ON_ACCENT": "#181825",     # text/icons drawn on the accent gradient
    "RED": "#f38ba8",
    "GREEN": "#a6e3a1",
    "ALT_ROW": "#212133",
    "LCD_TOP": "#141421",
    "LCD_BOTTOM": "#1a1a2b",
    "HANDLE_HOVER": "#ffffff",
}

LIGHT = {
    "BASE": "#f6f7fb",
    "MANTLE": "#eceef6",
    "PANEL": "#ffffff",
    "SURFACE": "#e3e6f1",
    "OVERLAY": "#cdd2e4",
    "BORDER": "#d8dcea",
    "TEXT": "#2a2e45",
    "SUBTEXT": "#5c6381",
    "MUTED": "#79809a",
    "ACCENT": "#3d68e0",
    "ACCENT2": "#7a4be8",
    "ACCENT_HOVER": "#2f58cc",
    "ACCENT2_HOVER": "#6a3ad0",
    "ON_ACCENT": "#ffffff",
    "RED": "#d1385c",
    "GREEN": "#2f9e58",
    "ALT_ROW": "#f0f2f9",
    "LCD_TOP": "#ffffff",
    "LCD_BOTTOM": "#f1f3fa",
    "HANDLE_HOVER": "#1e2233",
}

DARK["IS_DARK"], LIGHT["IS_DARK"] = True, False


def _mix(a: str, b: str, t: float) -> str:
    ca, cb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{max(0, min(255, round(x + (y - x) * t))):02x}" for x, y in zip(ca, cb))


def _palette(dark: bool, base: str, text: str, accent: str, accent2: str) -> dict:
    """A whole palette from four colours: the background, the text and two accents. Everything else (panels,
    borders, secondary text, hover shades) is derived so the pieces always sit together; the contrast test
    in tests/test_gui.py holds every theme to the same legibility rules."""
    white, black = "#ffffff", "#000000"
    if dark:
        mantle = _mix(base, black, .28)
        return {"IS_DARK": True, "BASE": base, "MANTLE": mantle, "PANEL": _mix(base, white, .06), "SURFACE": _mix(base, white, .12),
                "OVERLAY": _mix(base, white, .2), "BORDER": _mix(base, white, .09), "TEXT": text, "SUBTEXT": _mix(text, base, .36),
                "MUTED": _mix(text, base, .58), "ACCENT": accent, "ACCENT2": accent2, "ACCENT_HOVER": _mix(accent, white, .2),
                "ACCENT2_HOVER": _mix(accent2, white, .2), "ON_ACCENT": _mix(base, black, .45), "RED": "#f38ba8", "GREEN": "#a6e3a1",
                "ALT_ROW": _mix(base, mantle, .5), "LCD_TOP": _mix(base, black, .38), "LCD_BOTTOM": _mix(base, black, .2),
                "HANDLE_HOVER": white}
    return {"IS_DARK": False, "BASE": base, "MANTLE": _mix(base, black, .045), "PANEL": white, "SURFACE": _mix(base, black, .075),
            "OVERLAY": _mix(base, black, .16), "BORDER": _mix(base, black, .09), "TEXT": text, "SUBTEXT": _mix(text, base, .24),
            "MUTED": _mix(text, base, .42), "ACCENT": accent, "ACCENT2": accent2, "ACCENT_HOVER": _mix(accent, black, .14),
            "ACCENT2_HOVER": _mix(accent2, black, .14), "ON_ACCENT": white, "RED": "#c62f55", "GREEN": "#23824a",
            "ALT_ROW": _mix(base, black, .025), "LCD_TOP": white, "LCD_BOTTOM": _mix(base, black, .03), "HANDLE_HOVER": text}


# name -> (dark?, background, text, accent, second accent). Soft pastels first, then the deeper looks.
COLOR_THEMES = {
    "rose": (False, "#fdf1f5", "#3d2230", "#b83266", "#8a4fc4"),
    "lavender": (False, "#f5f1fd", "#2f2a4a", "#6444c2", "#b3408f"),
    "mint": (False, "#eef9f3", "#1f3a33", "#187a56", "#1f709e"),
    "sky": (False, "#f1f7fd", "#1f3145", "#1f68b8", "#7a55c9"),
    "peach": (False, "#fff4ec", "#42281a", "#b8501a", "#b83266"),
    "sand": (False, "#faf5e9", "#3d3524", "#8a5a00", "#2a7a6a"),
    "lagoon": (False, "#edf9fa", "#173a40", "#0e7c86", "#2f62c9"),
    "coral": (False, "#fff2ef", "#4a2320", "#b93a26", "#a85f0c"),
    "sage": (False, "#f1f5ec", "#2b3829", "#44762f", "#8a5a1f"),
    "lemon": (False, "#fdfae6", "#3b3818", "#7a6600", "#b3471a"),
    "forest": (True, "#10231a", "#e3f2e8", "#5fd39a", "#c5e063"),
    "ocean": (True, "#08192c", "#e6f5ff", "#22d3ff", "#6f9bff"),
    "sunset": (True, "#26121a", "#ffeee6", "#ff8a4c", "#ff5c9c"),
    "neon": (True, "#150a26", "#f6ecff", "#d868ff", "#2ee6ff"),
    "ember": (True, "#1c1414", "#fbeeea", "#ff5a4f", "#ffb84a"),
    "arctic": (True, "#2e3440", "#eceff4", "#88c0d0", "#b48ead"),
    "twilight": (True, "#282a36", "#f8f8f2", "#bd93f9", "#ff79c6"),
    "amber": (True, "#282524", "#ebdbb2", "#fabd2f", "#fe8019"),
    "rosewood": (True, "#191724", "#e0def4", "#eb6f92", "#c4a7e7"),
    "graphite": (True, "#1f2226", "#e6e8ea", "#4fd1c5", "#f6ad55"),
}

THEMES = {"dark": DARK, "light": LIGHT, **{name: _palette(*spec) for name, spec in COLOR_THEMES.items()}}

FONT_FAMILY = '"Inter", "Cantarell", "Roboto", "Noto Sans", "DejaVu Sans", sans-serif'
MONO_FAMILY = '"JetBrains Mono", "DejaVu Sans Mono", "Noto Sans Mono", monospace'


class _Signals(QObject):
    changed = Signal(str)   # "dark" | "light", after the palette attributes were updated


signals = _Signals()
NAME = "dark"
globals().update(DARK)


def set_theme(name: str) -> None:
    """Switch the module's colour attributes. Call ``signals.changed.emit`` once the app style is applied."""
    global NAME
    NAME = name if name in THEMES else "dark"
    globals().update(THEMES[NAME])


def is_dark() -> bool:
    return bool(THEMES.get(NAME, DARK).get("IS_DARK", True))


def rgba(hex_color: str, alpha: float) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"rgba({r},{g},{b},{round(alpha * 255)})"  # QSS wants 0-255, not 0-1


def qcolor(hex_color: str, alpha: int = 255):
    from PySide6.QtGui import QColor

    color = QColor(hex_color)
    color.setAlpha(alpha)
    return color


def build_stylesheet() -> str:
    g = globals()
    BASE, MANTLE, PANEL, SURFACE, OVERLAY, BORDER = (g[k] for k in ("BASE", "MANTLE", "PANEL", "SURFACE", "OVERLAY", "BORDER"))
    TEXT, SUBTEXT, MUTED, ACCENT, ACCENT2 = (g[k] for k in ("TEXT", "SUBTEXT", "MUTED", "ACCENT", "ACCENT2"))
    ACCENT_HOVER, ACCENT2_HOVER, ON_ACCENT = g["ACCENT_HOVER"], g["ACCENT2_HOVER"], g["ON_ACCENT"]
    ALT_ROW, LCD_TOP, LCD_BOTTOM, HANDLE_HOVER = g["ALT_ROW"], g["LCD_TOP"], g["LCD_BOTTOM"], g["HANDLE_HOVER"]
    return f"""
* {{ font-family: {FONT_FAMILY}; font-size: 13px; color: {TEXT}; outline: 0; }}
QMainWindow, QDialog {{ background: {BASE}; }}
QWidget#central {{ background: {BASE}; }}
QToolTip {{ background: {PANEL}; color: {TEXT}; border: 1px solid {OVERLAY}; border-radius: 6px; padding: 5px 8px; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {SUBTEXT}; }}
QPlainTextEdit#lyricsText {{ background: transparent; border: none; padding: 6px 18px 30px 18px; font-size: 16px; line-height: 150%; color: {SUBTEXT}; selection-background-color: transparent; }}
QWidget#lyricsPanel {{ background: {MANTLE}; border-left: 1px solid {BORDER}; }}
QLabel#credit {{ color: {MUTED}; font-size: 11px; letter-spacing: 0.4px; }}
QLabel#metaArt {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; color: {SUBTEXT}; }}
QLabel#heading {{ font-size: 15px; font-weight: 600; }}
QLabel#eqValue {{ font-family: {MONO_FAMILY}; font-size: 11px; color: {ACCENT}; }}
QWidget#eqDivider {{ background: {BORDER}; }}

/* Top bar & LCD ------------------------------------------------------------------ */
QWidget#topBar {{ background: {MANTLE}; border-bottom: 1px solid {BORDER}; }}
QFrame#lcd {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {LCD_TOP}, stop:1 {LCD_BOTTOM});
    border: 1px solid {BORDER}; border-radius: 14px;
}}
QLabel#lcdTitle {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
QLabel#lcdSub {{ color: {SUBTEXT}; }}
QLabel#lcdTime {{ font-family: {MONO_FAMILY}; font-size: 12px; color: {ACCENT}; }}
QLabel#lcdLive {{ color: {SUBTEXT}; font-size: 12px; }}
QLabel#cover {{ background: {PANEL}; border-radius: 10px; }}

QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QToolButton:hover {{ background: {SURFACE}; }}
QToolButton:pressed {{ background: {OVERLAY}; }}
QToolButton:checked {{ background: {rgba(ACCENT, 0.16)}; }}
QToolButton:disabled {{ background: transparent; }}
QToolButton#play {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT2});
    border-radius: 22px; padding: 0;
}}
QToolButton#play:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_HOVER}, stop:1 {ACCENT2_HOVER});
}}
QToolButton#menuButton::menu-indicator {{ image: none; }}

/* Sliders ------------------------------------------------------------------------- */
QSlider::groove:horizontal {{ height: 4px; background: {OVERLAY}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2});
    border-radius: 2px;
}}
QSlider::add-page:horizontal {{ background: {OVERLAY}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: {TEXT}; }}
/* the hover rules keep the geometry, and :hover belongs on the handle: as ":hover::handle" Qt
   paints the state across the whole bar (white on the dark theme, black on the light one) */
QSlider::handle:horizontal:hover {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: {HANDLE_HOVER}; }}
QSlider#seek::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: transparent; }}
QSlider#seek::handle:horizontal:hover {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: {HANDLE_HOVER}; }}
QSlider::groove:vertical {{ width: 4px; background: {OVERLAY}; border-radius: 2px; }}
QSlider::sub-page:vertical {{ background: {OVERLAY}; border-radius: 2px; }}
QSlider::add-page:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {ACCENT2}, stop:1 {ACCENT});
    border-radius: 2px;
}}
QSlider::handle:vertical {{ height: 14px; width: 14px; margin: 0 -5px; border-radius: 7px; background: {TEXT}; }}
QSlider::handle:vertical:hover {{ height: 14px; width: 14px; margin: 0 -5px; border-radius: 7px; background: {HANDLE_HOVER}; }}

/* Search field --------------------------------------------------------------------- */
QLineEdit {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 7px 12px; selection-background-color: {ACCENT}; selection-color: {ON_ACCENT};
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; background: {SURFACE}; }}

/* Sidebar ------------------------------------------------------------------------- */
QWidget#sidebarPanel {{ background: {MANTLE}; border-right: 1px solid {BORDER}; }}
QTreeWidget#sidebar {{ background: transparent; border: none; padding: 8px 8px 0 8px; }}
QToolButton#sidebarSettings {{
    text-align: left; padding: 9px 12px; border-radius: 9px; color: {SUBTEXT}; font-weight: 500;
}}
QToolButton#sidebarSettings:hover {{ background: {SURFACE}; color: {TEXT}; }}
QToolButton#sidebarSupport {{
    text-align: left; padding: 10px 14px; border-radius: 11px; font-weight: 600; color: {ACCENT};
    background: {rgba(ACCENT, 0.13)}; border: 1px solid {rgba(ACCENT, 0.42)};
}}
QToolButton#sidebarSupport:hover {{ background: {rgba(ACCENT, 0.24)}; border-color: {ACCENT}; color: {ACCENT_HOVER}; }}
QToolButton#sidebarSupport:pressed {{ background: {rgba(ACCENT, 0.32)}; }}

/* Track table ---------------------------------------------------------------------- */
QWidget#mainView {{ background: {BASE}; }}
QTableView {{
    background: {BASE}; alternate-background-color: {ALT_ROW}; border: none;
    gridline-color: transparent; selection-background-color: transparent; selection-color: {TEXT};
}}
QTableView::item {{ padding: 0 8px; border: none; }}
QTableView::item:hover {{ background: {rgba(ACCENT2, 0.07)}; }}
QTableView::item:selected {{ background: {rgba(ACCENT, 0.24)}; }}
QTreeWidget#deviceSongs {{ background: transparent; border: none; }}
QTreeWidget#deviceSongs::item {{ padding: 5px 6px; border-radius: 8px; }}
QTreeWidget#deviceSongs::item:hover {{ background: {SURFACE}; }}
QTreeWidget#deviceSongs::item:selected {{ background: {rgba(ACCENT, 0.24)}; }}
QHeaderView {{ background: {BASE}; }}
QHeaderView::section {{
    background: {BASE}; color: {SUBTEXT}; border: none; border-bottom: 1px solid {BORDER};
    padding: 8px 10px; font-size: 11px; font-weight: 600;
}}
QHeaderView::section:hover {{ color: {TEXT}; }}
QTableCornerButton::section {{ background: {BASE}; border: none; }}

/* Radio ------------------------------------------------------------------------------ */
QListWidget#stations {{ background: transparent; border: none; padding: 4px 14px; }}
QListWidget#stations::item {{ border: none; background: transparent; }}
QFrame#stationRow {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#stationRow:hover {{ background: {SURFACE}; }}
QFrame#stationRow[playing="true"] {{ border: 1px solid {ACCENT}; background: {rgba(ACCENT, 0.10)}; }}
QLabel#stationName {{ font-size: 14px; font-weight: 600; }}
QLabel#stationMeta {{ color: {SUBTEXT}; font-size: 12px; }}
QLabel#badge {{
    color: {SUBTEXT}; font-size: 11px; font-weight: 600; padding: 3px 8px;
    border: 1px solid {BORDER}; border-radius: 8px;
}}
QLabel#stationIcon {{ background: {SURFACE}; border-radius: 10px; }}
QPushButton#chip {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 15px; padding: 5px 14px; font-size: 12px; color: {SUBTEXT};
}}
QPushButton#chip:hover {{ color: {TEXT}; background: {SURFACE}; }}
QPushButton#chip:checked {{ color: {ON_ACCENT}; border: none; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2}); }}

/* Scrollbars ----------------------------------------------------------------------- */
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {OVERLAY}; border-radius: 4px; min-height: 36px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {OVERLAY}; border-radius: 4px; min-width: 36px; margin: 2px 0; }}
QScrollBar::handle:horizontal:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; border: none; height: 0; width: 0; }}

/* Buttons, combos, checks ------------------------------------------------------------ */
QPushButton {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 9px; padding: 7px 16px; font-weight: 500;
}}
QPushButton:hover {{ background: {OVERLAY}; }}
QPushButton:pressed {{ background: {PANEL}; }}
QPushButton:disabled {{ color: {MUTED}; background: {PANEL}; }}
QPushButton#primary {{
    color: {ON_ACCENT}; font-weight: 600; border: none;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2});
}}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_HOVER}, stop:1 {ACCENT2_HOVER}); }}
QPushButton#primary:disabled {{ background: {OVERLAY}; color: {MUTED}; }}
QComboBox {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 9px; padding: 6px 12px; min-height: 20px; }}
QComboBox:hover {{ border-color: {OVERLAY}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {OVERLAY}; border-radius: 8px; padding: 4px;
    selection-background-color: {rgba(ACCENT, 0.28)}; outline: 0;
}}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 34px; height: 20px; border-radius: 10px; background: {OVERLAY}; }}
QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2});
}}
QListWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; padding: 4px; }}
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {rgba(ACCENT, 0.24)}; }}
QListWidget::indicator {{ width: 18px; height: 18px; border-radius: 6px; background: {OVERLAY}; border: 1px solid {BORDER}; }}
QListWidget::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 12px; margin-top: 12px; padding: 14px 12px 10px 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {SUBTEXT}; font-weight: 600; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; color: {SUBTEXT}; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

/* Menus ----------------------------------------------------------------------------- */
QMenu {{ background: {PANEL}; border: 1px solid {OVERLAY}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 26px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {rgba(ACCENT, 0.26)}; }}
QMenu::item:disabled {{ color: {MUTED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 6px 8px; }}

/* Status bar, splitter, progress ------------------------------------------------------- */
QStatusBar {{ background: {MANTLE}; border-top: 1px solid {BORDER}; color: {SUBTEXT}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {SUBTEXT}; padding: 0 6px; }}
QSplitter::handle {{ background: {BORDER}; width: 1px; }}
QProgressBar {{ background: {OVERLAY}; border: none; border-radius: 3px; max-height: 6px; text-align: center; color: transparent; }}
QProgressBar::chunk {{
    border-radius: 3px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2});
}}
QMessageBox {{ background: {BASE}; }}
"""


def build_palette():
    """Palette for anything the QSS does not cover (dialog icons, native pickers)."""
    from PySide6.QtGui import QColor, QPalette

    g = globals()
    palette = QPalette()
    roles = {
        QPalette.Window: g["BASE"], QPalette.WindowText: g["TEXT"], QPalette.Base: g["PANEL"],
        QPalette.AlternateBase: g["BASE"], QPalette.Text: g["TEXT"], QPalette.Button: g["SURFACE"],
        QPalette.ButtonText: g["TEXT"], QPalette.ToolTipBase: g["PANEL"], QPalette.ToolTipText: g["TEXT"],
        QPalette.Highlight: g["ACCENT"], QPalette.HighlightedText: g["ON_ACCENT"],
        QPalette.PlaceholderText: g["MUTED"], QPalette.Link: g["ACCENT"],
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(g["MUTED"]))
    return palette
