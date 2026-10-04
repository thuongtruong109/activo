"""Render the app's bundled SVG icon sprite into reusable Qt icons."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


ICON_SPRITE_PATH = Path(__file__).with_name("assets") / "icons.svg"


@lru_cache(maxsize=128)
def icon_pixmap(name: str, size: int = 18, color: str | None = None) -> QPixmap:
    """Render one named vector icon at a device-independent square size."""
    renderer = QSvgRenderer(str(ICON_SPRITE_PATH))
    if not renderer.isValid() or not renderer.elementExists(name):
        raise ValueError(f"Unknown SVG icon: {name}")
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, name, QRectF(0, 0, size, size))
    if color is not None:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return pixmap


def svg_icon(name: str, size: int = 18, color: str | None = None) -> QIcon:
    """Return a QIcon backed by a rendered element from the SVG sprite."""
    return QIcon(icon_pixmap(name, size, color))
