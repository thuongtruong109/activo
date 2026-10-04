"""Application-wide widget rendering preferences."""

from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleOption, QWidget


class ApplicationStyle(QProxyStyle):
    """Keep Fusion behavior while suppressing native keyboard focus frames."""

    def __init__(self) -> None:
        super().__init__("Fusion")

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        if element != QStyle.PrimitiveElement.PE_FrameFocusRect:
            super().drawPrimitive(element, option, painter, widget)


def configure_widget_style(app: QApplication) -> None:
    app.setStyle(ApplicationStyle())
