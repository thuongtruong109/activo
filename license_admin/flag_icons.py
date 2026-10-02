"""Asynchronous FlagCDN SVG icons with a persistent local cache."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QObject,
    QRectF,
    QStandardPaths,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtSvg import QSvgRenderer


FLAG_CDN_TEMPLATE = "https://flagcdn.io/flags/4x3/{country_code}.svg"
FLAG_SIZE = (24, 18)


class FlagIconLoader(QObject):
    """Load flags without blocking startup, then cache the CDN response."""

    icon_loaded = Signal(str, QIcon)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        cache_root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )
        self._cache_directory = Path(cache_root) / "flags"
        self._pending: set[str] = set()

    def icon(self, country_code: str) -> QIcon:
        normalized = country_code.strip().lower()
        cached = self._cache_directory / f"{normalized}.svg"
        try:
            icon = self._render_svg(cached.read_bytes()) if cached.is_file() else QIcon()
        except OSError:
            icon = QIcon()
        if icon.isNull():
            icon = self._loading_placeholder()
            if os.environ.get("QT_QPA_PLATFORM", "").casefold() != "offscreen":
                self._request(normalized)
        return icon

    def _request(self, country_code: str) -> None:
        if country_code in self._pending:
            return
        self._pending.add(country_code)
        request = QNetworkRequest(
            QUrl(FLAG_CDN_TEMPLATE.format(country_code=country_code))
        )
        reply = self._manager.get(request)
        reply.finished.connect(
            lambda current=reply, code=country_code: self._finished(code, current)
        )

    def _finished(self, country_code: str, reply: QNetworkReply) -> None:
        self._pending.discard(country_code)
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            payload: QByteArray = reply.readAll()
            payload_bytes = bytes(payload.data())
            icon = self._render_svg(payload_bytes)
            if icon.isNull():
                return
            try:
                self._cache_directory.mkdir(parents=True, exist_ok=True)
                (self._cache_directory / f"{country_code}.svg").write_bytes(
                    payload_bytes
                )
            except OSError:
                pass
            self.icon_loaded.emit(country_code, icon)
        finally:
            reply.deleteLater()

    def _render_svg(self, payload: bytes) -> QIcon:
        renderer = QSvgRenderer(QByteArray(payload))
        if not renderer.isValid():
            return QIcon()
        width, height = FLAG_SIZE
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, width, height))
        painter.end()
        return QIcon(pixmap)

    def _loading_placeholder(self) -> QIcon:
        """Show a neutral flag silhouette while the CDN request is pending."""
        width, height = FLAG_SIZE
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#557084"), 1.4))
        painter.drawLine(4, 2, 4, 16)
        painter.drawRoundedRect(QRectF(5, 3, 15, 10), 1.5, 1.5)
        painter.end()
        return QIcon(pixmap)
