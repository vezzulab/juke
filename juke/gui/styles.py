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
    "MUTED": "#8a90aa",
    "ACCENT": "#3d68e0",
    "ACCENT2": "#8b5cf0",
    "ACCENT_HOVER": "#5a80ea",
    "ACCENT2_HOVER": "#a07af3",
    "ON_ACCENT": "#ffffff",
    "RED": "#d1385c",
    "GREEN": "#2f9e58",
    "ALT_ROW": "#f0f2f9",
    "LCD_TOP": "#ffffff",
    "LCD_BOTTOM": "#f1f3fa",
    "HANDLE_HOVER": "#1e2233",
}

THEMES = {"dark": DARK, "light": LIGHT}

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
    return NAME == "dark"


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
QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: {TEXT}; }}
QSlider::handle:horizontal:hover {{ background: {HANDLE_HOVER}; }}
QSlider#seek::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: transparent; }}
QSlider#seek:hover::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: {HANDLE_HOVER}; }}
QSlider::groove:vertical {{ width: 4px; background: {OVERLAY}; border-radius: 2px; }}
QSlider::sub-page:vertical {{ background: {OVERLAY}; border-radius: 2px; }}
QSlider::add-page:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {ACCENT2}, stop:1 {ACCENT});
    border-radius: 2px;
}}
QSlider::handle:vertical {{ height: 14px; width: 14px; margin: 0 -5px; border-radius: 7px; background: {TEXT}; }}
QSlider::handle:vertical:hover {{ background: {HANDLE_HOVER}; }}

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

/* Track table ---------------------------------------------------------------------- */
QWidget#mainView {{ background: {BASE}; }}
QTableView {{
    background: {BASE}; alternate-background-color: {ALT_ROW}; border: none;
    gridline-color: transparent; selection-background-color: transparent; selection-color: {TEXT};
}}
QTableView::item {{ padding: 0 8px; border: none; }}
QTableView::item:hover {{ background: {rgba(ACCENT2, 0.07)}; }}
QTableView::item:selected {{ background: {rgba(ACCENT, 0.24)}; }}
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
