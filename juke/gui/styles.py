"""Modern dark theme (QSS) and palette shared by the custom-painted widgets."""

from __future__ import annotations

# Palette -----------------------------------------------------------------------
BASE = "#1e1e2e"        # window background
MANTLE = "#181825"      # sidebar, deepest panels
PANEL = "#252538"       # secondary panels, cards
SURFACE = "#2f2f45"     # inputs, hovers
OVERLAY = "#3a3a55"     # borders on hover, slider grooves
BORDER = "#2b2b40"
TEXT = "#cdd6f4"
SUBTEXT = "#9399b2"
MUTED = "#6c7086"
ACCENT = "#7aa2f7"
ACCENT2 = "#cba6f7"
RED = "#f38ba8"
GREEN = "#a6e3a1"

FONT_FAMILY = '"Inter", "Cantarell", "Roboto", "Noto Sans", "DejaVu Sans", sans-serif'
MONO_FAMILY = '"JetBrains Mono", "DejaVu Sans Mono", "Noto Sans Mono", monospace'


def rgba(hex_color: str, alpha: float) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"rgba({r},{g},{b},{round(alpha * 255)})"  # QSS wants 0-255, not 0-1


def build_stylesheet() -> str:
    return f"""
* {{ font-family: {FONT_FAMILY}; font-size: 13px; color: {TEXT}; outline: 0; }}
QMainWindow, QDialog {{ background: {BASE}; }}
QWidget#central {{ background: {BASE}; }}
QToolTip {{ background: {PANEL}; color: {TEXT}; border: 1px solid {OVERLAY}; border-radius: 6px; padding: 5px 8px; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {SUBTEXT}; }}
QLabel#heading {{ font-size: 15px; font-weight: 600; }}

/* Top bar & LCD ------------------------------------------------------------------ */
QWidget#topBar {{ background: {MANTLE}; border-bottom: 1px solid {BORDER}; }}
QFrame#lcd {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #141421, stop:1 #1a1a2b);
    border: 1px solid {BORDER}; border-radius: 14px;
}}
QLabel#lcdTitle {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
QLabel#lcdSub {{ color: {SUBTEXT}; }}
QLabel#lcdTime {{ font-family: {MONO_FAMILY}; font-size: 12px; color: {ACCENT}; }}
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
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8fb1f9, stop:1 #d6b8fa);
}}
QToolButton#menuButton::menu-indicator {{ image: none; }}

/* Sliders ------------------------------------------------------------------------- */
QSlider::groove:horizontal {{ height: 4px; background: {OVERLAY}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2});
    border-radius: 2px;
}}
QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: {TEXT}; }}
QSlider::handle:horizontal:hover {{ background: #ffffff; }}
QSlider#seek::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: transparent; }}
QSlider#seek:hover::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: #ffffff; }}
QSlider::groove:vertical {{ width: 4px; background: {OVERLAY}; border-radius: 2px; }}
QSlider::sub-page:vertical {{ background: {OVERLAY}; border-radius: 2px; }}
QSlider::add-page:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {ACCENT2}, stop:1 {ACCENT});
    border-radius: 2px;
}}
QSlider::handle:vertical {{ height: 14px; width: 14px; margin: 0 -5px; border-radius: 7px; background: {TEXT}; }}
QSlider::handle:vertical:hover {{ background: #ffffff; }}

/* Search field --------------------------------------------------------------------- */
QLineEdit {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 7px 12px; selection-background-color: {ACCENT}; selection-color: {BASE};
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
    background: {BASE}; alternate-background-color: #212133; border: none;
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
    color: {BASE}; font-weight: 600; border: none;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2});
}}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8fb1f9, stop:1 #d6b8fa); }}
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
    """Dark palette so anything the QSS does not cover (dialog icons, native pickers) matches."""
    from PySide6.QtGui import QColor, QPalette

    palette = QPalette()
    roles = {
        QPalette.Window: BASE, QPalette.WindowText: TEXT, QPalette.Base: PANEL, QPalette.AlternateBase: BASE,
        QPalette.Text: TEXT, QPalette.Button: SURFACE, QPalette.ButtonText: TEXT, QPalette.ToolTipBase: PANEL,
        QPalette.ToolTipText: TEXT, QPalette.Highlight: ACCENT, QPalette.HighlightedText: BASE,
        QPalette.PlaceholderText: MUTED, QPalette.Link: ACCENT,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(MUTED))
    return palette
