"""Pure models for revision-bound Google Sheets synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from license_admin.domain import LicenseRecord


class SyncDirection(str, Enum):
    PUSH = "push"
    PULL = "pull"


class SyncTargetKind(str, Enum):
    GOOGLE_SHEET = "google-sheet"
    PUBLIC_CSV = "public-csv"


@dataclass(frozen=True, slots=True)
class SyncTarget:
    project_id: str
    spreadsheet_id: str
    worksheet: str
    kind: SyncTargetKind

    @property
    def settings_key(self) -> str:
        return (
            f"sync/{self.project_id}/{self.kind.value}/{self.spreadsheet_id}/"
            f"{self.worksheet}/baseline"
        )


@dataclass(frozen=True, slots=True)
class LocalSyncContext:
    target: SyncTarget
    revision: int
    digest: str


@dataclass(frozen=True, slots=True)
class SyncDiff:
    """Describe how destination records change when source records replace them."""

    added: tuple[LicenseRecord, ...]
    updated: tuple[LicenseRecord, ...]
    removed: tuple[LicenseRecord, ...]
    unchanged: tuple[LicenseRecord, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.updated or self.removed)


def _order(record: LicenseRecord) -> tuple[str, str]:
    return record.username.casefold(), record.hwid.casefold()


def build_sync_diff(
    source: tuple[LicenseRecord, ...] | list[LicenseRecord],
    destination: tuple[LicenseRecord, ...] | list[LicenseRecord],
) -> SyncDiff:
    """Return the deterministic replacement diff from destination to source."""
    desired = {record.hwid.casefold(): record for record in source}
    existing = {record.hwid.casefold(): record for record in destination}
    added = [record for key, record in desired.items() if key not in existing]
    updated = [
        record
        for key, record in desired.items()
        if key in existing and record.token != existing[key].token
    ]
    unchanged = [
        record
        for key, record in desired.items()
        if key in existing and record.token == existing[key].token
    ]
    removed = [record for key, record in existing.items() if key not in desired]
    return SyncDiff(
        added=tuple(sorted(added, key=_order)),
        updated=tuple(sorted(updated, key=_order)),
        removed=tuple(sorted(removed, key=_order)),
        unchanged=tuple(sorted(unchanged, key=_order)),
    )
