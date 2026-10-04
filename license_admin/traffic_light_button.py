"""Traffic light window actions with larger, transparent click areas."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPaintEvent, QPainter
from PySide6.QtWidgets import QPushButton

from license_admin.ui_metrics import CONTROL_HEIGHT


_COLORS = {
    "trafficClose": ("#ff5f57", "#ff756e", "#e0443e"),
    "trafficMinimize": ("#febc2e", "#ffca4b", "#e2a11d"),
    "trafficMaximize": ("#28c840", "#45d45a", "#1eac32"),
}


class TrafficLightButton(QPushButton):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setFixedSize(20, CONTROL_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._colors = _COLORS[name]

    def paintEvent(self, event: QPaintEvent) -> None:
        index = 2 if self.isDown() else 1 if self.underMouse() else 0
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._colors[index]))
        if not self.isEnabled():
            painter.setOpacity(0.45)
        painter.drawEllipse(QRectF((self.width() - 12) / 2, (self.height() - 12) / 2, 12, 12))
