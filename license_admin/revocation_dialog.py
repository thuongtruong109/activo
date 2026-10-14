"""Searchable revocation history with publication status and a direct publish action."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from license_admin.localization import text
from license_admin.qt_models import normalize_search_text
from license_admin.responsive import fit_window_to_screen, wrap_label
from license_admin.revocations import RevocationEntry, RevocationPhase


class RevocationDialog(QDialog):
    remove_requested = Signal(str)

    def __init__(
        self, parent: QWidget, entries: tuple[RevocationEntry, ...], *, can_publish: bool,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(text("publication.review"))
        layout = QVBoxLayout(self)
        self._can_publish = can_publish
        self.summary = QLabel()
        wrap_label(self.summary)
        layout.addWidget(self.summary)
        self.search = QLineEdit()
        self.search.setPlaceholderText(text("dashboard.search"))
        self.search.setAccessibleName(text("accessibility.search_licenses"))
        layout.addWidget(self.search)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            text("table.user"), "HWID", text("table.status"), "JTI",
            text("revocations.time"), text("revocations.published"),
        ])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 270)
        self.table.setColumnWidth(2, 170)
        layout.addWidget(self.table, 1)
        self.search.textChanged.connect(self._filter)
        actions = QHBoxLayout()
        self.publish_button = QPushButton(text("publication.publish"))
        self.publish_button.setObjectName("primaryButton")
        self.publish_button.clicked.connect(self.accept)
        actions.addWidget(self.publish_button)
        self.remove_button = QPushButton(text("action.remove_device"))
        self.remove_button.clicked.connect(self._remove_selected)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        close = QPushButton(text("common.close"))
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.table.itemSelectionChanged.connect(self._update_remove)
        self.set_entries(entries)
        fit_window_to_screen(self, QSize(940, 520))

    def set_entries(self, entries: tuple[RevocationEntry, ...]) -> None:
        self._entries = sorted(entries, key=lambda item: (
            item.phase is RevocationPhase.PUBLISHED, -item.revoked_at.timestamp()
        ))
        self.table.setRowCount(len(self._entries))
        self._search_values = []
        for row, entry in enumerate(self._entries):
            state = text("revocations.pending" if entry.phase is not RevocationPhase.PUBLISHED else "revocations.done")
            if entry.remove_device:
                state += " / " + text("action.remove_device")
            values = (entry.username or "—", entry.hwid, state, entry.jti or "—",
                      entry.revoked_at.strftime("%d/%m/%Y %H:%M"),
                      entry.published_at.strftime("%d/%m/%Y %H:%M") if entry.published_at else "—")
            self._search_values.append(normalize_search_text(" ".join(values)))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 2 and entry.phase is not RevocationPhase.PUBLISHED:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, column, item)
        pending = sum(entry.phase is not RevocationPhase.PUBLISHED for entry in entries)
        self.summary.setText(text("revocations.summary", count=pending))
        self.publish_button.setEnabled(self._can_publish and bool(pending))
        self._filter(self.search.text())
        self._update_remove()

    def _update_remove(self) -> None:
        row = self.table.currentRow()
        self.remove_button.setEnabled(self._can_publish and 0 <= row < len(self._entries)
                                      and not self._entries[row].remove_device)

    def _remove_selected(self) -> None:
        row = self.table.currentRow()
        if self.remove_button.isEnabled() and 0 <= row < len(self._entries):
            self.remove_requested.emit(self._entries[row].hwid)

    def _filter(self, value: str) -> None:
        query = normalize_search_text(value)
        for row, haystack in enumerate(self._search_values):
            self.table.setRowHidden(row, bool(query and query not in haystack))
