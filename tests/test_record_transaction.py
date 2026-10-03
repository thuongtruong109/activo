from __future__ import annotations

from collections.abc import Iterable
import unittest

from issue_license import LicenseIssueError
from license_admin.domain import LicenseRecord
from license_admin.record_transaction import RecordTransaction


class RecordingRepository:
    def __init__(self) -> None:
        self.saved: tuple[LicenseRecord, ...] | None = None

    def save(self, records: Iterable[LicenseRecord]) -> None:
        self.saved = tuple(records)


class RecordTransactionTests(unittest.TestCase):
    def test_candidate_builders_never_mutate_published_records(self) -> None:
        first = LicenseRecord(hwid="first", token="old", username="Zulu")
        second = LicenseRecord(hwid="second", token="old", username="Alpha")
        replacement = LicenseRecord(
            hwid="first-new",
            token="new",
            username="Beta",
        )
        imported = LicenseRecord(hwid="second", token="imported", username="Gamma")
        published = [first, second]

        upsert = RecordTransaction.upsert(
            published,
            replacement,
            original_hwid=first.hwid,
        )
        revoked = RecordTransaction.revoke(published, first.hwid)
        merged = RecordTransaction.merge(published, [imported])

        self.assertEqual(published, [first, second])
        self.assertEqual(upsert.snapshot, (second, replacement))
        self.assertEqual(revoked.snapshot, (second,))
        self.assertEqual(merged.snapshot, (imported, first))

    def test_commit_validates_before_calling_repository(self) -> None:
        duplicate = RecordTransaction.from_records(
            [
                LicenseRecord(hwid="ABC", token="one"),
                LicenseRecord(hwid="abc", token="two"),
            ]
        )
        repository = RecordingRepository()

        with self.assertRaisesRegex(LicenseIssueError, "duplicate HWID"):
            duplicate.commit(repository)

        self.assertIsNone(repository.saved)

    def test_commit_returns_persisted_immutable_snapshot(self) -> None:
        record = LicenseRecord(hwid="first", token="token")
        transaction = RecordTransaction.from_records([record])
        repository = RecordingRepository()

        committed = transaction.commit(repository)

        self.assertIs(committed, transaction.snapshot)
        self.assertEqual(repository.saved, transaction.snapshot)


if __name__ == "__main__":
    unittest.main()
