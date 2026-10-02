"""Reusable presentation widgets for the License Admin dashboard."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QCursor, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

from license_admin.icons import icon_pixmap, svg_icon


class SidebarButton(QPushButton):
    def __init__(self, text: str, icon_name: str, *, active: bool = False) -> None:
        super().__init__(text)
        self._label = text
        self.setObjectName("sidebarButton")
        self.setProperty("active", active)
        self.setIcon(svg_icon(icon_name))
        self.setIconSize(QSize(17, 17))
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._active_indicator = QFrame(self)
        self._active_indicator.setObjectName("activeNavIndicator")
        self._active_indicator.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self._active_indicator.setVisible(active)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._active_indicator.setGeometry(0, (self.height() - 18) // 2, 3, 18)

    def set_label(self, label: str) -> None:
        self._label = label
        self.setText("" if self.property("collapsed") else label)
        self.setToolTip(label if self.property("collapsed") else "")

    def set_collapsed(self, collapsed: bool) -> None:
        self.setProperty("collapsed", collapsed)
        self.setText("" if collapsed else self._label)
        self.setToolTip(self._label if collapsed else "")
        self.style().unpolish(self)
        self.style().polish(self)


class SidebarMenuButton(QToolButton):
    def __init__(self, text: str, icon_name: str) -> None:
        super().__init__()
        self._label = text
        self.setText(text)
        self.setObjectName("sidebarButton")
        self.setIcon(svg_icon(icon_name))
        self.setIconSize(QSize(17, 17))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._chevron = QLabel(self)
        self._chevron.setPixmap(icon_pixmap("chevron-right", 13))
        self._chevron.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._chevron.setFixedSize(13, 13)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._chevron.move(self.width() - 23, (self.height() - 13) // 2)

    def set_label(self, label: str) -> None:
        self._label = label
        self.setText("" if self.property("collapsed") else label)
        self.setToolTip(label if self.property("collapsed") else "")

    def set_collapsed(self, collapsed: bool) -> None:
        self.setProperty("collapsed", collapsed)
        self.setText("" if collapsed else self._label)
        self.setToolTip(self._label if collapsed else "")
        self.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if collapsed
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._chevron.setVisible(not collapsed)
        self.style().unpolish(self)
        self.style().polish(self)


class MetricCard(QFrame):
    def __init__(
        self,
        title: str,
        note: str,
        icon_name: str,
        accent: str,
    ) -> None:
        super().__init__()
        self.setObjectName("metricCard")
        self.setMinimumHeight(112)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 14, 14)
        layout.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(5)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("metricTitle")
        self.value_label = QLabel("0")
        self.value_label.setObjectName("metricValue")
        self.note_label = QLabel(note)
        self.note_label.setObjectName("metricNote")
        copy.addWidget(self.title_label)
        copy.addWidget(self.value_label)
        copy.addWidget(self.note_label)
        copy.addStretch(1)

        icon = QLabel()
        icon.setObjectName("metricIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(34, 34)
        icon.setPixmap(icon_pixmap(icon_name, 18))
        accent_color = QColor(accent)
        icon.setStyleSheet(
            "QLabel {"
            f" color: {accent};"
            f" background: rgba({accent_color.red()}, {accent_color.green()}, "
            f"{accent_color.blue()}, 24);"
            f" border: 1px solid rgba({accent_color.red()}, {accent_color.green()}, "
            f"{accent_color.blue()}, 48);"
            " border-radius: 17px; font-size: 16px; font-weight: 700;"
            "}"
        )
        layout.addLayout(copy, 1)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

    def set_value(self, value: int) -> None:
        self.value_label.setText(f"{value:,}".replace(",", "."))

    def set_texts(self, title: str, note: str) -> None:
        self.title_label.setText(title)
        self.note_label.setText(note)
