"""Reusable frameless-window chrome and resize handles."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainterPath, QRegion
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QTabBar,
    QToolButton,
    QWidget,
)

from license_admin.localization import text


APP_HEADER_HEIGHT = 58


def enable_frameless_window(window: QWidget) -> None:
    """Remove native title chrome while retaining a normal top-level window."""
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


def _toggle_maximized(window: QWidget) -> None:
    if window.isMaximized():
        window.showNormal()
    else:
        window.showMaximized()


class DraggableFrame(QFrame):
    """A blank frame area that delegates moving to the window manager."""

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            _toggle_maximized(self.window())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class WindowChromeBar(DraggableFrame):
    """Compact macOS-style close, minimize and zoom controls."""

    def __init__(self, target: QWidget) -> None:
        super().__init__()
        self._target = target
        self.setObjectName("windowChrome")
        self.setFixedHeight(APP_HEADER_HEIGHT)

        layout = QHBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)
        self.close_button = self._button(
            "trafficClose",
            text("chrome.close"),
            target.close,
        )
        self.minimize_button = self._button(
            "trafficMinimize",
            text("chrome.minimize"),
            target.showMinimized,
        )
        self.maximize_button = self._button(
            "trafficMaximize",
            text("chrome.maximize"),
            lambda: _toggle_maximized(target),
        )
        layout.addWidget(self.close_button)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addStretch(1)

    def add_trailing_widget(self, widget: QWidget) -> None:
        self._layout.insertWidget(self._layout.count() - 1, widget)

    def retranslate(self) -> None:
        self.close_button.setToolTip(text("chrome.close"))
        self.minimize_button.setToolTip(text("chrome.minimize"))
        self.maximize_button.setToolTip(text("chrome.maximize"))

    def _button(
        self,
        object_name: str,
        tooltip: str,
        callback: Callable[[], object],
    ) -> QPushButton:
        button = QPushButton()
        button.setObjectName(object_name)
        button.setToolTip(tooltip)
        button.setFixedSize(12, 12)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        return button


class FramelessTabHeader(QFrame):
    """A fixed dialog header where the tab list is the title content."""

    current_changed = Signal(int)

    def __init__(self, target: QWidget) -> None:
        super().__init__()
        self.setObjectName("settingsHeader")
        self.setFixedHeight(42)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(0)

        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("settingsTabBar")
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.currentChanged.connect(self.current_changed.emit)
        layout.addWidget(self.tab_bar)
        layout.addStretch(1)

        self.close_button = QToolButton()
        self.close_button.setObjectName("modalCloseButton")
        self.close_button.setText("×")
        self.close_button.setToolTip(text("chrome.close"))
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFixedSize(28, 28)
        self.close_button.clicked.connect(target.close)
        layout.addWidget(self.close_button)

    def add_tab(self, label: str) -> int:
        return self.tab_bar.addTab(label)


class _ResizeHandle(QWidget):
    def __init__(
        self,
        target: QWidget,
        edges: Qt.Edge,
        cursor: Qt.CursorShape,
    ) -> None:
        super().__init__(target)
        self._target = target
        self._edges = edges
        self.setCursor(cursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._target.windowHandle()
            if handle is not None and handle.startSystemResize(self._edges):
                event.accept()
                return
        super().mousePressEvent(event)


class FramelessResizeController(QObject):
    """Keep thin native resize hit areas around a frameless window."""

    _BORDER = 5
    _CORNER = 11

    def __init__(self, target: QWidget, *, corner_radius: int = 12) -> None:
        super().__init__(target)
        self._target = target
        self._corner_radius = corner_radius
        self._handles = (
            _ResizeHandle(target, Qt.Edge.TopEdge, Qt.CursorShape.SizeVerCursor),
            _ResizeHandle(target, Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor),
            _ResizeHandle(target, Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor),
            _ResizeHandle(target, Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor),
            _ResizeHandle(
                target,
                Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
                Qt.CursorShape.SizeFDiagCursor,
            ),
            _ResizeHandle(
                target,
                Qt.Edge.TopEdge | Qt.Edge.RightEdge,
                Qt.CursorShape.SizeBDiagCursor,
            ),
            _ResizeHandle(
                target,
                Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
                Qt.CursorShape.SizeBDiagCursor,
            ),
            _ResizeHandle(
                target,
                Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
                Qt.CursorShape.SizeFDiagCursor,
            ),
        )
        target.installEventFilter(self)
        self._update_handles()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._target and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.WindowStateChange,
        }:
            self._update_handles()
        return super().eventFilter(watched, event)

    def _update_handles(self) -> None:
        width = self._target.width()
        height = self._target.height()
        self._update_window_mask(width, height)
        border = self._BORDER
        corner = self._CORNER
        geometries = (
            QRect(corner, 0, max(0, width - 2 * corner), border),
            QRect(corner, max(0, height - border), max(0, width - 2 * corner), border),
            QRect(0, corner, border, max(0, height - 2 * corner)),
            QRect(max(0, width - border), corner, border, max(0, height - 2 * corner)),
            QRect(0, 0, corner, corner),
            QRect(max(0, width - corner), 0, corner, corner),
            QRect(0, max(0, height - corner), corner, corner),
            QRect(
                max(0, width - corner),
                max(0, height - corner),
                corner,
                corner,
            ),
        )
        visible = not self._target.isMaximized()
        for handle, geometry in zip(self._handles, geometries, strict=True):
            handle.setGeometry(geometry)
            handle.setVisible(visible)
            handle.raise_()

    def _update_window_mask(self, width: int, height: int) -> None:
        if self._target.isMaximized() or self._target.isFullScreen():
            self._target.clearMask()
            return
        if width < 1 or height < 1:
            return
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(0, 0, width, height),
            self._corner_radius,
            self._corner_radius,
        )
        self._target.setMask(QRegion(path.toFillPolygon().toPolygon()))
