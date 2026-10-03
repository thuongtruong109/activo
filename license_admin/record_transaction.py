"""Application transaction for publishing license-record snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from issue_license import LicenseIssueError
from license_admin.domain import LicenseRecord


class RecordWriter(Protocol):
    def save(self, records: Iterable[LicenseRecord]) -> None: ...


def _record_order(record: LicenseRecord) -> tuple[str, str]:
    return record.username.casefold(), record.hwid


@dataclass(frozen=True, slots=True)
class RecordTransaction:
    """Hold an unpublished snapshot until its repository write succeeds."""

    snapshot: tuple[LicenseRecord, ...]

    @classmethod
    def from_records(cls, records: Iterable[LicenseRecord]) -> RecordTransaction:
        return cls(tuple(records))

    @classmethod
    def sorted_records(cls, records: Iterable[LicenseRecord]) -> RecordTransaction:
        return cls(tuple(sorted(records, key=_record_order)))

    @classmethod
    def upsert(
        cls,
        current: Iterable[LicenseRecord],
        record: LicenseRecord,
        *,
        original_hwid: str | None,
    ) -> RecordTransaction:
        candidate = [
            item
            for item in current
            if original_hwid is None or item.hwid != original_hwid
        ]
        candidate.append(record)
        return cls.sorted_records(candidate)

    @classmethod
    def revoke(
        cls,
        current: Iterable[LicenseRecord],
        hwid: str,
    ) -> RecordTransaction:
        return cls.from_records(item for item in current if item.hwid != hwid)

    @classmethod
    def merge(
        cls,
        current: Iterable[LicenseRecord],
        imported: Iterable[LicenseRecord],
    ) -> RecordTransaction:
        merged = {record.hwid: record for record in current}
        merged.update({record.hwid: record for record in imported})
        return cls.sorted_records(merged.values())

    def commit(self, repository: RecordWriter) -> tuple[LicenseRecord, ...]:
        """Validate and persist the snapshot without mutating application state."""
        seen_hwids: set[str] = set()
        for record in self.snapshot:
            if not isinstance(record, LicenseRecord):
                raise LicenseIssueError("The license snapshot contains an invalid record.")
            normalized_hwid = record.hwid.casefold()
            if normalized_hwid in seen_hwids:
                raise LicenseIssueError(
                    f"The license snapshot contains duplicate HWID {record.hwid!r}."
                )
            seen_hwids.add(normalized_hwid)
        repository.save(self.snapshot)
        return self.snapshot
