from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from issue_license import LicenseIssueError
from license_admin.domain import LicenseRecord
from license_admin.license_state import LicenseStateTransaction
from license_admin.record_transaction import RecordTransaction
from license_admin.revocations import (
    RevocationRepository,
    request_revocation,
)
from license_admin.storage import LicenseRepository
from workspace_temp import workspace_temp_dir


class LicenseStateTransactionTests(unittest.TestCase):
    def test_record_failure_restores_previous_revocation_journal(self) -> None:
        now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        active = LicenseRecord(
            hwid="a" * 64,
            token="token",
            username="User",
            jti="b" * 32,
        )
        with workspace_temp_dir() as directory:
            root = Path(directory)
            records = LicenseRepository(root / "licenses.csv")
            revocations = RevocationRepository(root / "licenses.revocations.json")
            records.save([active])
            original_records = records.path.read_bytes()
            original_journal = revocations.save(())
            transaction = LicenseStateTransaction(
                RecordTransaction.revoke([active], active.hwid),
                request_revocation((), active, now=now),
            )

            with (
                patch.object(
                    records,
                    "save",
                    side_effect=LicenseIssueError("simulated record failure"),
                ),
                self.assertRaisesRegex(LicenseIssueError, "simulated record failure"),
            ):
                transaction.commit(records, revocations)

            self.assertEqual(revocations.load(), original_journal)
            self.assertEqual(records.path.read_bytes(), original_records)


if __name__ == "__main__":
    unittest.main()
