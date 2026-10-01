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


class SidebarMenuButton(QToolButton):
    def __init__(self, text: str, icon_name: str) -> None:
        super().__init__()
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
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        self.value_label = QLabel("0")
        self.value_label.setObjectName("metricValue")
        note_label = QLabel(note)
        note_label.setObjectName("metricNote")
        copy.addWidget(title_label)
        copy.addWidget(self.value_label)
        copy.addWidget(note_label)
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


class ProjectIdentityCard(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("projectIdentity")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(9)
        self.avatar_label = QLabel("L")
        self.avatar_label.setObjectName("projectAvatar")
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setFixedSize(34, 34)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        self.name_label = QLabel()
        self.name_label.setObjectName("projectName")
        self.id_label = QLabel()
        self.id_label.setObjectName("projectId")
        copy.addWidget(self.name_label)
        copy.addWidget(self.id_label)
        layout.addWidget(self.avatar_label)
        layout.addLayout(copy, 1)

    def set_project(self, name: str, project_id: str) -> None:
        self.name_label.setText(name)
        self.id_label.setText(project_id)
        initial = next((character for character in name.strip() if character.isalnum()), "L")
        self.avatar_label.setText(initial.upper())
