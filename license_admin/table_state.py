"""Contextual empty, recovery, and network states for the license table."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from license_admin.icons import icon_pixmap
from license_admin.responsive import WrappedLabel


class TableStatePanel(QFrame):
    """A single reusable table replacement with context-specific actions."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("tableStatePanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._primary_callback: Callable[[], None] | None = None
        self._secondary_callback: Callable[[], None] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(8)
        layout.addStretch(1)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("tableStateIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedSize(44, 44)
        layout.addWidget(
            self.icon_label,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        self.title_label = QLabel()
        self.title_label.setObjectName("tableStateTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        self.body_label = WrappedLabel()
        self.body_label.setObjectName("tableStateBody")
        self.body_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_label.setMaximumWidth(560)
        layout.addWidget(self.body_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)
        self.primary_button = QPushButton()
        self.primary_button.setObjectName("primaryButton")
        self.primary_button.clicked.connect(self._run_primary)
        actions.addWidget(self.primary_button)
        self.secondary_button = QPushButton()
        self.secondary_button.clicked.connect(self._run_secondary)
        actions.addWidget(self.secondary_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)

    def set_content(
        self,
        *,
        state: str,
        icon_name: str,
        title: str,
        body: str,
        primary_label: str,
        primary_callback: Callable[[], None],
        secondary_label: str = "",
        secondary_callback: Callable[[], None] | None = None,
    ) -> None:
        self.setProperty("state", state)
        self.icon_label.setPixmap(icon_pixmap(icon_name, 24))
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.primary_button.setText(primary_label)
        self.primary_button.setAccessibleName(primary_label)
        self._primary_callback = primary_callback
        self.secondary_button.setText(secondary_label)
        self.secondary_button.setAccessibleName(secondary_label)
        self.secondary_button.setVisible(bool(secondary_label and secondary_callback))
        self._secondary_callback = secondary_callback
        self.setAccessibleName(title)
        self.setAccessibleDescription(body)
        self.style().unpolish(self)
        self.style().polish(self)

    def _run_primary(self) -> None:
        if self._primary_callback is not None:
            self._primary_callback()

    def _run_secondary(self) -> None:
        if self._secondary_callback is not None:
            self._secondary_callback()
