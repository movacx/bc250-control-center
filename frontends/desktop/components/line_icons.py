"""Thin line glyphs drawn in the colour the caller asks for.

The shipped icon set comes in fixed colours (a red stop, a blue terminal);
the built-in terminal's header wants one quiet ink for all of them, matched to
the terminal theme in use. Each glyph is a small SVG path set, recoloured and
rendered on demand.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSize
from PyQt6.QtGui import QIcon, QPixmap

_HEAD = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
)

GLYPHS = {
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2.5"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4l-8 8"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "close": '<path d="M7 7l10 10M17 7L7 17"/>',
}


def line_icon(name: str, color: str, size: int = 32) -> QIcon:
    svg = _HEAD.format(color=color) + GLYPHS[name] + "</svg>"
    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(svg.encode("utf-8")), "SVG")
    if pixmap.isNull():
        return QIcon()
    return QIcon(pixmap.scaled(QSize(size, size)))
