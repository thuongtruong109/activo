"""Shared scroll containers and screen-aware initial window sizing."""

from PySide6.QtCore import QSize
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QWidget,
)


def fit_window_to_screen(
    window: QWidget,
    preferred: QSize,
    minimum: QSize = QSize(440, 300),
) -> None:
    screen = window.screen()
    available = screen.availableGeometry().size() if screen is not None else preferred
    limit = QSize(max(240, available.width() - 24), max(200, available.height() - 40))
    window.setMinimumSize(minimum.boundedTo(limit))
    window.resize(preferred.boundedTo(limit))


def scroll_container(body: QWidget, *, name: str = "responsiveScroll") -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName(name)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setMinimumSize(0, 0)
    scroll.setWidget(body)
    scroll.viewport().setAutoFillBackground(False)
    body.setAutoFillBackground(False)
    return scroll


def responsive_form(form: QFormLayout) -> None:
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    for row in range(form.rowCount()):
        item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        label = item.widget() if item is not None else None
        if isinstance(label, QLabel):
            label.setWordWrap(True)
            policy = label.sizePolicy()
            policy.setVerticalPolicy(QSizePolicy.Policy.Minimum)
            label.setSizePolicy(policy)


def wrap_label(
    label: QLabel,
    *,
    vertical_policy: QSizePolicy.Policy = QSizePolicy.Policy.Minimum,
) -> None:
    """Allow long text to shrink while preserving Qt's height-for-width flag."""
    label.setWordWrap(True)
    policy = label.sizePolicy()
    policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
    policy.setVerticalPolicy(vertical_policy)
    policy.setHeightForWidth(True)
    label.setSizePolicy(policy)


class WrappedLabel(QLabel):
    """Keep centered wrapped text tall enough for its actual assigned width."""

    def __init__(self) -> None:
        super().__init__()
        wrap_label(self)

    def setText(self, value: str) -> None:
        super().setText(value)
        self._update_minimum_height()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_minimum_height()

    def _update_minimum_height(self) -> None:
        self.setMinimumHeight(max(0, self.heightForWidth(self.width())))
