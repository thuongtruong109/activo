"""Non-blocking toast notifications for the license-admin window."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from license_admin.icons import icon_pixmap
from license_admin.accessibility import announce, set_accessible_text
from license_admin.localization import text


class Toast(QFrame):
    """A reusable bottom-right notification that never blocks interaction."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setProperty("tone", "success")
        set_accessible_text(self, name=text("accessibility.notification"))
        self.setMinimumWidth(320)
        self.setMaximumWidth(460)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(8)
        self._icon = QLabel()
        self._icon.setObjectName("toastIcon")
        self._icon.setFixedSize(18, 18)
        self._icon.setPixmap(icon_pixmap("toast-success", 18))
        self._message = QLabel()
        self._message.setObjectName("toastMessage")
        self._message.setWordWrap(True)
        self._message.setMaximumWidth(420)
        layout.addWidget(self._icon)
        layout.addWidget(self._message, 1)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._animation = QPropertyAnimation(self._opacity, b"opacity", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._animation_finished)
        self._hiding = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(
        self,
        message: str,
        *,
        tone: str = "success",
        duration_ms: int = 3_800,
    ) -> None:
        self._timer.stop()
        self._animation.stop()
        self._hiding = False
        self.setProperty("tone", tone)
        self._icon.setPixmap(
            icon_pixmap("toast-success" if tone == "success" else "toast-info", 18)
        )
        self._message.setText(message)
        set_accessible_text(
            self,
            name=text("accessibility.notification"),
            description=message,
        )
        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()
        self.reposition()
        self._opacity.setOpacity(0.0)
        self.show()
        self.raise_()
        announce(self, message)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.start()
        self._timer.start(duration_ms)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 14
        self.move(
            max(margin, parent.width() - self.width() - margin),
            max(margin, parent.height() - self.height() - margin),
        )

    def _fade_out(self) -> None:
        self._animation.stop()
        self._hiding = True
        self._animation.setStartValue(self._opacity.opacity())
        self._animation.setEndValue(0.0)
        self._animation.start()

    def _animation_finished(self) -> None:
        if self._hiding:
            self._hiding = False
            self.hide()
