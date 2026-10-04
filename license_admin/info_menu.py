"""Independent information actions in one keyboard-accessible header menu."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolButton, QWidget

from license_admin.icons import svg_icon
from license_admin.localization import text
from license_admin.popover import RoundedMenu
from license_admin.ui_metrics import CONTROL_HEIGHT


class InformationMenuButton(QToolButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerInfoButton")
        self._compact = False
        self.setFixedHeight(CONTROL_HEIGHT)
        self.setIcon(svg_icon("about", 16))
        self.setIconSize(QSize(16, 16))
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setShortcut("F1")
        menu = RoundedMenu(parent=self)
        self.setMenu(menu)
        self.about_action = QAction(svg_icon("about"), "", self)
        self.policy_action = QAction(svg_icon("shield"), "", self)
        self.terms_action = QAction(svg_icon("document"), "", self)
        menu.addActions([self.about_action, self.policy_action, self.terms_action])
        self.retranslate()

    def retranslate(self) -> None:
        label = text("info.help")
        self.setText(label)
        self.setToolTip(label)
        self.setAccessibleName(label)
        self.menu().setTitle(label)
        for action, key in (
            (self.about_action, "info.about"),
            (self.policy_action, "info.privacy"),
            (self.terms_action, "info.terms"),
        ):
            action.setText(text(key))
        self.set_compact(self._compact)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setProperty("compact", compact)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)
        self.setFixedWidth(CONTROL_HEIGHT if compact else self.sizeHint().width() + 8)
