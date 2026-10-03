"""Atomic application transaction for active records plus revocation journal."""

from __future__ import annotations

from dataclasses import dataclass

from issue_license import LicenseIssueError
from license_admin.domain import LicenseRecord
from license_admin.record_transaction import RecordTransaction
from license_admin.revocations import RevocationEntry, RevocationRepository
from license_admin.storage import LicenseRepository


@dataclass(frozen=True, slots=True)
class LicenseStateSnapshot:
    records: tuple[LicenseRecord, ...]
    revocations: tuple[RevocationEntry, ...]


class LicenseStateTransaction:
    """Persist tombstones first, with rollback if active-record persistence fails."""

    def __init__(
        self,
        records: RecordTransaction,
        revocations: tuple[RevocationEntry, ...],
    ) -> None:
        self.records = records
        self.revocations = revocations

    def commit(
        self,
        record_repository: LicenseRepository,
        revocation_repository: RevocationRepository,
    ) -> LicenseStateSnapshot:
        active_hwids = {record.hwid.casefold() for record in self.records.snapshot}
        revoked_hwids = {entry.hwid.casefold() for entry in self.revocations}
        overlap = active_hwids & revoked_hwids
        if overlap:
            raise LicenseIssueError(
                f"An HWID cannot be both active and revoked: {sorted(overlap)[0]!r}."
            )
        prior_revocations = revocation_repository.snapshot_bytes()
        committed_revocations = revocation_repository.save(self.revocations)
        try:
            committed_records = self.records.commit(record_repository)
        except Exception as exc:
            try:
                revocation_repository.restore_bytes(prior_revocations)
            except LicenseIssueError as rollback_exc:
                raise LicenseIssueError(
                    f"Unable to persist license state: {exc}. "
                    f"Revocation rollback also failed: {rollback_exc}"
                ) from exc
            raise
        return LicenseStateSnapshot(committed_records, committed_revocations)
