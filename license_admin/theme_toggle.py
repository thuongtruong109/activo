"""Compact two-option theme selector for the application header."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from license_admin.localization import text
from license_admin.icons import svg_icon
from license_admin.theme import semantic_palette_for
from license_admin.ui_metrics import CONTROL_HEIGHT


class ThemeToggle(QFrame):
    """Segmented Light/Dark control with a single active option."""

    mode_changed = Signal(str)

    def __init__(self, mode: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("themeTabs")
        self.setFixedSize(72, CONTROL_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self.light_button = QPushButton()
        self.light_button.setObjectName("themeLightTab")
        self.dark_button = QPushButton()
        self.dark_button.setObjectName("themeDarkTab")
        for button in (self.light_button, self.dark_button):
            button.setCheckable(True)
            button.setIconSize(QSize(16, 16))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(button, 1)

        self.light_button.clicked.connect(lambda: self.set_mode("light", emit=True))
        self.dark_button.clicked.connect(lambda: self.set_mode("dark", emit=True))
        self._mode = "dark"
        self.retranslate()
        self.set_mode(mode)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str, *, emit: bool = False) -> None:
        normalized = "light" if mode == "light" else "dark"
        changed = normalized != self._mode
        self._mode = normalized
        self._set_active(self.light_button, normalized == "light")
        self._set_active(self.dark_button, normalized == "dark")
        palette = semantic_palette_for(normalized)
        selected_color = "#ffffff" if normalized == "dark" else "#1f2c3d"
        self.light_button.setIcon(svg_icon("sun", 16, selected_color if normalized == "light" else palette.icon))
        self.dark_button.setIcon(svg_icon("moon", 16, selected_color if normalized == "dark" else palette.icon))
        if emit and changed:
            self.mode_changed.emit(normalized)

    def retranslate(self) -> None:
        for button, label in (
            (self.light_button, text("theme.light")),
            (self.dark_button, text("theme.dark")),
        ):
            button.setText("")
            button.setAccessibleName(label)
            button.setToolTip(label)

    @staticmethod
    def _set_active(button: QPushButton, active: bool) -> None:
        button.setChecked(active)
        button.setProperty("active", active)
        button.style().unpolish(button)
        button.style().polish(button)
