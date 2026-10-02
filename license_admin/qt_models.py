"""Qt models used by the license-admin dashboard."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor

from license_admin.domain import LicenseRecord, LicenseStatus
from license_admin.localization import text


STATUS_LABEL_KEYS = {
    LicenseStatus.ACTIVE: "status.active",
    LicenseStatus.EXPIRING: "status.expiring",
    LicenseStatus.EXPIRED: "status.expired",
    LicenseStatus.FUTURE: "status.future",
    LicenseStatus.INVALID: "status.invalid",
}

STATUS_COLORS = {
    LicenseStatus.ACTIVE: QColor("#22c55e"),
    LicenseStatus.EXPIRING: QColor("#f59e0b"),
    LicenseStatus.EXPIRED: QColor("#ef4444"),
    LicenseStatus.FUTURE: QColor("#60a5fa"),
    LicenseStatus.INVALID: QColor("#f87171"),
}


def normalize_search_text(value: str) -> str:
    """Normalize case and Vietnamese diacritics for contains-style search."""
    folded = value.strip().casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )


class LicenseTableModel(QAbstractTableModel):
    HEADER_KEYS = (
        "table.user",
        "HWID",
        "table.status",
        "table.expires",
        "table.remaining",
        "table.issued",
        "JTI",
    )

    def __init__(self) -> None:
        super().__init__()
        self._records: list[LicenseRecord] = []

    @property
    def records(self) -> list[LicenseRecord]:
        return list(self._records)

    def set_records(self, records: list[LicenseRecord]) -> None:
        self.beginResetModel()
        self._records = list(records)
        self.endResetModel()

    def record_at(self, row: int) -> LicenseRecord | None:
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> int:
        return 0 if parent.isValid() else len(self._records)

    def columnCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> int:
        return 0 if parent.isValid() else len(self.HEADER_KEYS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                key = self.HEADER_KEYS[section]
                return key if key in {"HWID", "JTI"} else text(key)
            return section + 1
        if (
            role == Qt.ItemDataRole.TextAlignmentRole
            and orientation == Qt.Orientation.Vertical
        ):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._records):
            return None
        record = self._records[index.row()]
        status = record.status()
        values: tuple[Any, ...] = (
            record.username or "—",
            record.hwid,
            text(STATUS_LABEL_KEYS[status]),
            self._format_datetime(record.expires_at),
            self._remaining(record),
            self._format_datetime(record.issued_at),
            record.jti or "—",
        )
        if role == Qt.ItemDataRole.DisplayRole:
            return values[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return record
        if role == Qt.ItemDataRole.UserRole + 1:
            sort_values: tuple[Any, ...] = (
                record.username.casefold(),
                record.hwid,
                status.value,
                record.expires_at.timestamp() if record.expires_at else -1,
                record.remaining_days() if record.remaining_days() is not None else -1,
                record.issued_at.timestamp() if record.issued_at else -1,
                record.jti or "",
            )
            return sort_values[index.column()]
        if role == Qt.ItemDataRole.ForegroundRole and index.column() == 2:
            return STATUS_COLORS[status]
        if role == Qt.ItemDataRole.ToolTipRole:
            if record.parse_error:
                return record.parse_error
            if index.column() == 1:
                return record.hwid
            if index.column() == 6:
                return record.jti
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in (2, 4):
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "—"
        return value.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M")

    @staticmethod
    def _remaining(record: LicenseRecord) -> str:
        days = record.remaining_days()
        if days is None:
            return "—"
        return text("table.days", count=days)

    def retranslate(self) -> None:
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 6)
        if self._records:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._records) - 1, 6),
                [int(Qt.ItemDataRole.DisplayRole)],
            )


class LicenseFilterModel(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self._query = ""
        self._status: LicenseStatus | None = None
        self.setSortRole(int(Qt.ItemDataRole.UserRole) + 1)
        self.setDynamicSortFilter(True)

    def set_query(self, value: str) -> None:
        self.beginFilterChange()
        self._query = normalize_search_text(value)
        self.endFilterChange()

    def set_status(self, status: LicenseStatus | None) -> None:
        self.beginFilterChange()
        self._status = status
        self.endFilterChange()

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        source = self.sourceModel()
        if not isinstance(source, LicenseTableModel):
            return True
        record = source.record_at(source_row)
        if record is None:
            return False
        if self._status is not None and record.status() is not self._status:
            return False
        if not self._query:
            return True
        searchable = normalize_search_text(
            " ".join((record.username, record.hwid, record.jti or "", record.token))
        )
        return self._query in searchable
