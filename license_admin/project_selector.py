"""Compact, card-style project selector used by the dashboard header."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QAction, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QWidget,
    QWidgetAction,
)

from license_admin.accessibility import set_accessible_text
from license_admin.localization import text
from license_admin.popover import PopoverSelect
from license_admin.ui_metrics import CONTROL_HEIGHT


class ProjectSelector(PopoverSelect):
    """A readable one-line project selector with full identity metadata."""

    pinned_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("projectSelector")
        self.setFixedHeight(CONTROL_HEIGHT)
        self.setMinimumWidth(160)
        self.setMaximumWidth(240)
        self._full_name = ""
        self._project_id = ""
        self._pinned_ids: set[str] = set()
        self._recent_ids: list[str] = []
        self._section_actions: list[QAction] = []

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(text("project.search"))
        self._search_edit.setAccessibleName(text("project.search"))
        self._search_edit.textChanged.connect(self._filter_menu)
        self._search_action = QWidgetAction(self)
        self._search_action.setDefaultWidget(self._search_edit)
        self._pin_action = QAction(self)
        self._pin_action.triggered.connect(self._toggle_current_pin)
        self.menu().aboutToShow.connect(self._prepare_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 22, 3)
        layout.setSpacing(6)

        self.avatar_label = QLabel("L")
        self.avatar_label.setObjectName("projectSelectorAvatar")
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setFixedSize(24, 24)
        self.avatar_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        self.name_label = QLabel()
        self.name_label.setObjectName("projectSelectorName")
        self.name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(self.avatar_label)
        layout.addWidget(self.name_label, 1)

    def clear_items(self) -> None:
        self._section_actions.clear()
        super().clear_items()
        self._full_name = ""
        self._project_id = ""
        self.avatar_label.setText("L")
        self.name_label.clear()
        self.setToolTip("")
        set_accessible_text(self, name=text("nav.current_project"))

    def set_pinned_ids(self, project_ids: set[str]) -> None:
        self._pinned_ids = set(project_ids)

    def pinned_ids(self) -> set[str]:
        return set(self._pinned_ids)

    def retranslate(self) -> None:
        self._search_edit.setPlaceholderText(text("project.search"))
        self._search_edit.setAccessibleName(text("project.search"))
        self._update_pin_action()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._render_name()

    def _select_action(self, action: QAction, *, emit: bool) -> None:
        super()._select_action(action, emit=emit)
        name = action.text()
        project_id = action.data()
        initial = next(
            (character for character in name.strip() if character.isalnum()),
            "L",
        )
        self.avatar_label.setText(initial.upper())
        self._full_name = name
        self._project_id = str(project_id)
        if self._project_id in self._recent_ids:
            self._recent_ids.remove(self._project_id)
        self._recent_ids.insert(0, self._project_id)
        del self._recent_ids[5:]
        self._render_name()
        identity = f"{text('settings.project_id')}: {self._project_id}"
        self.setToolTip(f"{name}\n{identity}")
        action.setToolTip(identity)
        set_accessible_text(
            self,
            name=f"{text('nav.current_project')}: {name}",
            description=identity,
        )
        # The child labels render the selected project; suppress native button text.
        self.setText("")
        self._update_pin_action()

    def _render_name(self) -> None:
        available = max(24, self.name_label.width())
        self.name_label.setText(
            self.name_label.fontMetrics().elidedText(
                self._full_name,
                Qt.TextElideMode.ElideRight,
                available,
            )
        )

    def _prepare_menu(self) -> None:
        menu = self.menu()
        menu.clear()
        self._section_actions.clear()

        actions_by_id = {
            str(action.data()): action for action in self.actions()
        }
        categories: list[tuple[str, list[QAction]]] = []
        pinned = sorted(
            (
                action
                for project_id, action in actions_by_id.items()
                if project_id in self._pinned_ids
            ),
            key=lambda action: action.text().casefold(),
        )
        if pinned:
            categories.append((text("project.pinned"), pinned))
        recent = [
            actions_by_id[project_id]
            for project_id in self._recent_ids
            if project_id in actions_by_id and project_id not in self._pinned_ids
        ]
        if recent:
            categories.append((text("project.recent"), recent))
        used = {action for _label, actions in categories for action in actions}
        remaining = sorted(
            (action for action in self.actions() if action not in used),
            key=lambda action: action.text().casefold(),
        )
        if remaining:
            categories.append((text("project.all"), remaining))

        if len(self.actions()) >= 5:
            self._search_edit.clear()
            menu.addAction(self._search_action)
            menu.addSeparator()
            QTimer.singleShot(0, self._search_edit.setFocus)
        for label, actions in categories:
            section = menu.addSection(label)
            self._section_actions.append(section)
            for action in actions:
                menu.addAction(action)
                action.setProperty("projectSection", label)
        if len(self.actions()) > 1:
            menu.addSeparator()
            self._update_pin_action()
            menu.addAction(self._pin_action)

    def _filter_menu(self, query: str) -> None:
        normalized = query.strip().casefold()
        for action in self.actions():
            identity = str(action.data()).casefold()
            action.setVisible(
                not normalized
                or normalized in action.text().casefold()
                or normalized in identity
            )
        for section in self._section_actions:
            label = section.text()
            section.setVisible(
                any(
                    action.isVisible()
                    and action.property("projectSection") == label
                    for action in self.actions()
                )
            )

    def _toggle_current_pin(self) -> None:
        if not self._project_id:
            return
        if self._project_id in self._pinned_ids:
            self._pinned_ids.remove(self._project_id)
        else:
            self._pinned_ids.add(self._project_id)
        self._update_pin_action()
        self.pinned_changed.emit(tuple(sorted(self._pinned_ids)))

    def _update_pin_action(self) -> None:
        pinned = self._project_id in self._pinned_ids
        label = text("project.unpin_current" if pinned else "project.pin_current")
        self._pin_action.setText(label)
