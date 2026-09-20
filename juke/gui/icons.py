"""Vector (SVG) icons rendered on demand at the screen's device pixel ratio.

Nothing raster is shipped: every glyph below is an SVG fragment recoloured and
rasterised by QtSvg for the exact size and scale factor, so icons stay sharp on
HiDPI and fractional-scaling Wayland sessions.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..assets import ICON_SVG
from . import styles

# name -> (kind, body). "stroke" glyphs are outlines, "fill" glyphs are solid shapes.
_GLYPHS: dict[str, tuple[str, str]] = {
    "play": ("fill", '<path d="M8 5.2v13.6a.6.6 0 0 0 .9.5l11-6.8a.6.6 0 0 0 0-1l-11-6.8a.6.6 0 0 0-.9.5z"/>'),
    "pause": ("fill", '<rect x="6" y="5" width="4" height="14" rx="1.2"/><rect x="14" y="5" width="4" height="14" rx="1.2"/>'),
    "prev": ("fill", '<rect x="5.5" y="5.5" width="2.4" height="13" rx="1.1"/><path d="M19 6.3v11.4a.5.5 0 0 1-.8.4l-8-5.7a.5.5 0 0 1 0-.8l8-5.7a.5.5 0 0 1 .8.4z"/>'),
    "next": ("fill", '<rect x="16.1" y="5.5" width="2.4" height="13" rx="1.1"/><path d="M5 6.3v11.4a.5.5 0 0 0 .8.4l8-5.7a.5.5 0 0 0 0-.8l-8-5.7a.5.5 0 0 0-.8.4z"/>'),
    "stop": ("fill", '<rect x="6" y="6" width="12" height="12" rx="2.4"/>'),
    "volume": ("stroke", '<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" fill="currentColor"/><path d="M15.5 9a4 4 0 0 1 0 6M18.3 6.3a8 8 0 0 1 0 11.4"/>'),
    "mute": ("stroke", '<path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" fill="currentColor"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>'),
    "eq": ("stroke", '<path d="M6 4v16M12 4v16M18 4v16"/><circle cx="6" cy="15" r="2.2" fill="currentColor"/><circle cx="12" cy="8" r="2.2" fill="currentColor"/><circle cx="18" cy="13" r="2.2" fill="currentColor"/>'),
    "shuffle": ("stroke", '<path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/>'),
    "repeat": ("stroke", '<path d="M17 2l4 4-4 4M3 12V10a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 12v2a4 4 0 0 1-4 4H3"/>'),
    "repeat-one": ("stroke", '<path d="M17 2l4 4-4 4M3 12V10a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 12v2a4 4 0 0 1-4 4H3M11 10l1.6-1.2V15"/>'),
    "search": ("stroke", '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>'),
    "heart": ("fill", '<path d="M12 20.6s-7.6-4.6-9.6-9.7A5.4 5.4 0 0 1 12 6.2a5.4 5.4 0 0 1 9.6 4.7c-2 5.1-9.6 9.7-9.6 9.7z"/>'),
    "note": ("stroke", '<path d="M9 18V5.5l11-2V16"/><circle cx="6" cy="18" r="3" fill="currentColor"/><circle cx="17" cy="16" r="3" fill="currentColor"/>'),
    "artist": ("stroke", '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7.5" r="4"/>'),
    "album": ("stroke", '<circle cx="12" cy="12" r="9.5"/><circle cx="12" cy="12" r="2.6"/>'),
    "genre": ("stroke", '<path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z"/><circle cx="7" cy="7" r="1.4" fill="currentColor"/>'),
    "server": ("stroke", '<rect x="2.5" y="3" width="19" height="7.5" rx="2"/><rect x="2.5" y="13.5" width="19" height="7.5" rx="2"/><path d="M6.5 6.8h.01M6.5 17.3h.01"/>'),
    "clock": ("stroke", '<circle cx="12" cy="12" r="9.5"/><path d="M12 6.5V12l3.8 2.2"/>'),
    "queue": ("stroke", '<path d="M4 6h12M4 12h12M4 18h7"/><path d="M17.5 14.5v6l4.5-3z" fill="currentColor"/>'),
    "gear": ("stroke", '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'),
    "more": ("stroke", '<circle cx="5" cy="12" r="1.7" fill="currentColor"/><circle cx="12" cy="12" r="1.7" fill="currentColor"/><circle cx="19" cy="12" r="1.7" fill="currentColor"/>'),
    "playlist": ("stroke", '<path d="M4 6h16M4 12h16M4 18h9"/><path d="M17 18h4M19 16v4"/>'),
    "sliders": ("stroke", '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1.5 14h5M9.5 8h5M17.5 16h5"/>'),
    "refresh": ("stroke", '<path d="M22 4v6h-6M2 20v-6h6"/><path d="M3.5 9a9 9 0 0 1 14.9-3.4L22 10M2 14l3.6 4.4A9 9 0 0 0 20.5 15"/>'),
    "folder": ("stroke", '<path d="M21.5 18.5a2 2 0 0 1-2 2h-15a2 2 0 0 1-2-2v-13a2 2 0 0 1 2-2h4.5l2 3h8.5a2 2 0 0 1 2 2z"/>'),
    "trash": ("stroke", '<path d="M4 7h16M9 7V4h6v3M6.5 7l1 13h9l1-13"/>'),
    "close": ("stroke", '<path d="M6 6l12 12M18 6L6 18"/>'),
    "plus": ("stroke", '<path d="M12 5v14M5 12h14"/>'),
    "chevron": ("stroke", '<path d="M9 6l6 6-6 6"/>'),
}


def _svg(name: str, color: str) -> bytes:
    kind, body = _GLYPHS[name]
    body = body.replace("currentColor", color)
    if kind == "fill":
        attrs = f'fill="{color}" stroke="none"'
    else:
        attrs = f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {attrs}>{body}</svg>'.encode()


def _dpr() -> float:
    screen = QGuiApplication.primaryScreen()
    return screen.devicePixelRatio() if screen else 1.0


def render_svg(data: bytes | str, size: int, dpr: float | None = None) -> QPixmap:
    """Rasterise SVG ``data`` to a ``size``x``size`` (logical px) pixmap, crisp at any scale."""
    dpr = dpr or _dpr()
    px = max(1, int(round(size * dpr)))
    image = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    renderer = QSvgRenderer(QByteArray(data if isinstance(data, bytes) else data.encode()))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


@lru_cache(maxsize=256)
def _cached_glyph(name: str, color: str, size: int, dpr: float) -> QPixmap:
    return render_svg(_svg(name, color), size, dpr)


def glyph(name: str, color: str = styles.TEXT, size: int = 20) -> QPixmap:
    return _cached_glyph(name, color, size, _dpr())


def icon(name: str, color: str = styles.SUBTEXT, active: str | None = None,
         disabled: str = styles.MUTED, size: int = 24) -> QIcon:
    """QIcon with normal/checked/disabled variants (``active`` = colour when checked)."""
    result = QIcon()
    for scale in (1.0, 1.25, 1.5, 2.0, 3.0):
        result.addPixmap(_cached_glyph(name, color, size, scale), QIcon.Normal, QIcon.Off)
        result.addPixmap(_cached_glyph(name, active or color, size, scale), QIcon.Normal, QIcon.On)
        result.addPixmap(_cached_glyph(name, disabled, size, scale), QIcon.Disabled, QIcon.Off)
        result.addPixmap(_cached_glyph(name, disabled, size, scale), QIcon.Disabled, QIcon.On)
    return result


_PLACEHOLDER = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#34344f"/><stop offset="1" stop-color="#232336"/></linearGradient></defs>'
    '<rect width="96" height="96" rx="14" fill="url(#g)"/>'
    '<g transform="translate(28 28) scale(1.7)" fill="none" stroke="#6c7086" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M9 18V5.5l11-2V16"/><circle cx="6" cy="18" r="3" fill="#6c7086"/><circle cx="17" cy="16" r="3" fill="#6c7086"/></g>'
    '</svg>'
)


def placeholder_cover(size: int) -> QPixmap:
    return render_svg(_PLACEHOLDER, size)


def app_icon() -> QIcon:
    result = QIcon()
    result.addFile(str(ICON_SVG))
    return result
