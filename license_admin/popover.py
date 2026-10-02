"""Reusable rounded popover menus and select buttons."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QMenu, QSizePolicy, QToolButton, QWidget


class RoundedMenu(QMenu):
    """Shared popup surface with transparent native corners."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.setObjectName("roundedPopover")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)


class PopoverSelect(QToolButton):
    """QMenu-backed selector used consistently across the dashboard."""

    selection_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("popoverSelect")
        self.setProperty("popover", True)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._menu = RoundedMenu(parent=self)
        self.setMenu(self._menu)
        self._group = QActionGroup(self)
        self._group.setExclusive(True)
        self._group.triggered.connect(self._action_selected)
        self._actions: list[QAction] = []
        self._current_data: Any = None

    def add_item(
        self,
        text: str,
        data: Any,
        *,
        icon: QIcon | None = None,
    ) -> QAction:
        action = QAction(icon or QIcon(), text, self._group)
        action.setCheckable(True)
        action.setData(data)
        self._menu.addAction(action)
        self._actions.append(action)
        if len(self._actions) == 1:
            self._select_action(action, emit=False)
        return action

    def clear_items(self) -> None:
        self._menu.clear()
        for action in self._actions:
            self._group.removeAction(action)
            action.deleteLater()
        self._actions.clear()
        self._current_data = None
        self.setText("")
        self.setIcon(QIcon())

    def current_data(self) -> Any:
        return self._current_data

    def currentData(self) -> Any:
        """Qt-style compatibility alias used by existing callers."""
        return self.current_data()

    def set_current_data(self, data: Any, *, emit: bool = False) -> bool:
        for action in self._actions:
            if action.data() == data:
                self._select_action(action, emit=emit)
                return True
        return False

    def set_item_icon(self, data: Any, icon: QIcon) -> None:
        for action in self._actions:
            if action.data() == data:
                action.setIcon(icon)
                if data == self._current_data:
                    self.setIcon(icon)
                return

    def set_item_text(self, data: Any, text: str) -> None:
        for action in self._actions:
            if action.data() == data:
                action.setText(text)
                if data == self._current_data:
                    self.setText(text)
                return

    def actions(self) -> list[QAction]:
        return list(self._actions)

    def _action_selected(self, action: QAction) -> None:
        self._select_action(action, emit=True)

    def _select_action(self, action: QAction, *, emit: bool) -> None:
        action.setChecked(True)
        self._current_data = action.data()
        self.setText(action.text())
        self.setIcon(action.icon())
        if emit:
            self.selection_changed.emit(self._current_data)
