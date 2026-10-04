"""Dashboard breakpoints, kept outside the license operation controller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLayout

from license_admin.localization import text
from license_admin.window_chrome import APP_HEADER_HEIGHT

if TYPE_CHECKING:
    from license_admin.main_window import LicenseAdminWindow


def _clear_layout(layout: QLayout) -> None:
    while layout.count():
        layout.takeAt(0)


def _clear_grid(layout: QGridLayout) -> None:
    _clear_layout(layout)
    for column in range(layout.columnCount()):
        layout.setColumnStretch(column, 0)


class DashboardResponsiveController:
    def __init__(self, window: LicenseAdminWindow) -> None:
        self.window = window
        self._signature: tuple[bool, bool, int, bool] | None = None
        _clear_grid(window.top_bar_layout)
        self._primary_row = QHBoxLayout()
        self._utility_row = QHBoxLayout()
        self._primary_row.setSpacing(8)
        self._utility_row.setSpacing(8)
        window.top_bar_layout.addLayout(self._primary_row, 0, 0)
        window.top_bar_layout.addLayout(self._utility_row, 1, 0)

    def update_layout(self, *, force: bool = False) -> None:
        window = self.window
        auto_collapsed = window.width() < 1100
        collapsed = auto_collapsed or window._sidebar_preferred_collapsed
        available = window.width() - (72 if collapsed else 220)
        # Use translated control hints to account for longer locale labels.
        header_width = (
            window.project_combo.minimumWidth()
            + window.primary_action_button.fontMetrics().horizontalAdvance(text("action.new_license"))
            + 42
            + window.info_button.fontMetrics().horizontalAdvance(text("info.help"))
            + 44
            + window.theme_toggle.sizeHint().width()
            + window.language_selector.width()
            + window.window_controls.sizeHint().width()
            + 88
        )
        narrow_header = available < max(760, header_width)
        columns = 2 if available < 880 else 4
        narrow_filters = available < 740
        signature = (collapsed, narrow_header, columns, narrow_filters)
        if signature == self._signature and not force:
            return
        self._signature = signature
        window._set_sidebar_collapsed(collapsed)
        window.sidebar_toggle.setEnabled(not auto_collapsed)
        if auto_collapsed:
            window.sidebar_toggle.setToolTip(text("nav.sidebar_compact"))
            window.sidebar_toggle.setAccessibleDescription(text("nav.sidebar_compact"))

        layout = window.top_bar_layout
        _clear_layout(self._primary_row)
        _clear_layout(self._utility_row)
        window.info_button.set_compact(narrow_header)
        window.primary_action_button.setText("" if narrow_header else text("action.new_license"))
        window.primary_action_button.setToolTip(text("action.new_license"))
        # Clear the previous fixed width before measuring the translated label.
        window.primary_action_button.setMinimumWidth(0)
        window.primary_action_button.setMaximumWidth(16777215)
        window.primary_action_button.setFixedWidth(
            36 if narrow_header else window.primary_action_button.sizeHint().width()
        )
        alignment = Qt.AlignmentFlag.AlignVCenter
        self._primary_row.addWidget(window.project_combo, 0, alignment)
        self._primary_row.addWidget(window.primary_action_button, 0, alignment)
        self._primary_row.addStretch(1)
        if narrow_header:
            self._primary_row.addWidget(window.window_controls, 0, alignment)
            self._utility_row.addWidget(window.info_button, 0, alignment)
            self._utility_row.addStretch(1)
            self._utility_row.addWidget(window.theme_toggle, 0, alignment)
            self._utility_row.addWidget(window.language_selector, 0, alignment)
        else:
            for widget in (
                window.info_button, window.theme_toggle,
                window.language_selector, window.window_controls,
            ):
                self._primary_row.addWidget(widget, 0, alignment)
        layout.setVerticalSpacing(4 if narrow_header else 0)
        window.top_bar.setFixedHeight(APP_HEADER_HEIGHT + (36 if narrow_header else 0))

        _clear_grid(window.metrics_layout)
        for index, card in enumerate(window.metric_cards):
            window.metrics_layout.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            window.metrics_layout.setColumnStretch(column, 1)

        filters = window.table_header_layout
        _clear_grid(filters)
        if narrow_filters:
            filters.addWidget(window.table_filters, 0, 0, 1, 3)
            filters.addWidget(window.visible_label, 1, 0)
            filters.addWidget(window.sync_badge, 1, 2, Qt.AlignmentFlag.AlignRight)
        else:
            filters.addWidget(window.table_filters, 0, 0)
            filters.addWidget(window.visible_label, 0, 1)
            filters.addWidget(window.sync_badge, 0, 2)
        filters.setColumnStretch(0, 1)
