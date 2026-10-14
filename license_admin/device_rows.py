"""Device table rows, separate from the active token snapshot used for publishing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from license_admin.domain import LicenseRecord, LicenseStatus
from license_admin.revocations import RevocationEntry, RevocationPhase


@dataclass(frozen=True, slots=True)
class DeviceRow:
    record: LicenseRecord
    revocation: RevocationEntry | None = None

    def status(self) -> LicenseStatus:
        return LicenseStatus.REVOKED if self.revocation else self.record.status()

    @property
    def awaiting_publication(self) -> bool:
        return (
            self.revocation is not None
            and self.revocation.phase is not RevocationPhase.PUBLISHED
        )


def build_device_rows(
    records: Iterable[LicenseRecord], revocations: Iterable[RevocationEntry],
) -> list[DeviceRow]:
    """Retain revoked devices without exposing their former token or removed rows."""
    entries = {entry.hwid: entry for entry in revocations}
    rows = [DeviceRow(record) for record in records if record.hwid not in entries]
    rows.extend(
        DeviceRow(
            LicenseRecord(hwid=entry.hwid, token="", username=entry.username, jti=entry.jti),
            revocation=entry,
        )
        for entry in entries.values()
        if not entry.remove_device
    )
    return rows
