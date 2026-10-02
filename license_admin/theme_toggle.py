"""Compact two-option theme selector for the application header."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from license_admin.localization import text
from license_admin.ui_metrics import CONTROL_HEIGHT


class ThemeToggle(QFrame):
    """Segmented Light/Dark control with a single active option."""

    mode_changed = Signal(str)

    def __init__(self, mode: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("themeTabs")
        self.setFixedSize(120, CONTROL_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self.light_button = QPushButton()
        self.light_button.setObjectName("themeLightTab")
        self.dark_button = QPushButton()
        self.dark_button.setObjectName("themeDarkTab")
        for button in (self.light_button, self.dark_button):
            button.setCheckable(True)
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
        if emit and changed:
            self.mode_changed.emit(normalized)

    def retranslate(self) -> None:
        self.light_button.setText(text("theme.light"))
        self.dark_button.setText(text("theme.dark"))

    @staticmethod
    def _set_active(button: QPushButton, active: bool) -> None:
        button.setChecked(active)
        button.setProperty("active", active)
        button.style().unpolish(button)
        button.style().polish(button)
