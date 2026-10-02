"""Compact, card-style project selector used by the dashboard header."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from license_admin.popover import PopoverSelect


class ProjectSelector(PopoverSelect):
    """A two-line project identity card that also opens a selection menu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("projectSelector")
        self.setFixedHeight(42)
        self.setMinimumWidth(184)
        self.setMaximumWidth(240)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 24, 4)
        layout.setSpacing(8)

        self.avatar_label = QLabel("L")
        self.avatar_label.setObjectName("projectSelectorAvatar")
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setFixedSize(30, 30)
        self.avatar_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(0)
        self.name_label = QLabel()
        self.name_label.setObjectName("projectSelectorName")
        self.id_label = QLabel()
        self.id_label.setObjectName("projectSelectorId")
        for label in (self.name_label, self.id_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        copy.addWidget(self.name_label)
        copy.addWidget(self.id_label)

        layout.addWidget(self.avatar_label)
        layout.addLayout(copy, 1)

    def clear_items(self) -> None:
        super().clear_items()
        self.avatar_label.setText("L")
        self.name_label.clear()
        self.id_label.clear()

    def _select_action(self, action: QAction, *, emit: bool) -> None:
        super()._select_action(action, emit=emit)
        name = action.text()
        project_id = action.data()
        initial = next(
            (character for character in name.strip() if character.isalnum()),
            "L",
        )
        self.avatar_label.setText(initial.upper())
        self.name_label.setText(name)
        self.id_label.setText(str(project_id))
        # The child labels render the selected project; suppress native button text.
        self.setText("")
