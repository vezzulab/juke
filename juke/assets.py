"""Locate bundled resources (icon, fonts) regardless of how Juke is installed."""

from __future__ import annotations

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICON_SVG = ASSETS_DIR / "juke.svg"
FONTS_DIR = ASSETS_DIR / "fonts"
