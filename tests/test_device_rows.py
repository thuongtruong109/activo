from datetime import datetime, timezone
import unittest

from license_admin.device_rows import build_device_rows
from license_admin.domain import LicenseRecord, LicenseStatus
from license_admin.revocations import RevocationEntry, RevocationPhase


class DeviceRowsTests(unittest.TestCase):
    def test_revocation_wins_over_stale_active_tokens_and_removal_hides_the_row(self):
        now = datetime.now(timezone.utc)
        records = [LicenseRecord("a" * 64, "old secret"), LicenseRecord("b" * 64, "removed secret"),
                   LicenseRecord("c" * 64, "active token")]
        entries = (
            RevocationEntry("a" * 64, "a" * 32, "Revoked customer", now, RevocationPhase.PENDING),
            RevocationEntry("b" * 64, None, "Removed customer", now, RevocationPhase.PENDING,
                            remove_device=True),
        )
        rows = build_device_rows(records, entries)
        self.assertEqual({row.record.hwid for row in rows}, {"a" * 64, "c" * 64})
        revoked = next(row for row in rows if row.record.hwid == "a" * 64)
        self.assertEqual(revoked.record.token, "")
        self.assertEqual(revoked.record.username, "Revoked customer")
        self.assertEqual(revoked.record.jti, "a" * 32)
        self.assertIs(revoked.status(), LicenseStatus.REVOKED)
        self.assertTrue(revoked.awaiting_publication)
        self.assertEqual(records[0].token, "old secret")

    def test_published_and_prepared_revocations_remain_visible_without_active_records(self):
        now = datetime.now(timezone.utc)
        entries = (
            RevocationEntry("a" * 64, None, "Published", now, RevocationPhase.PUBLISHED,
                            published_at=now, published_revision=1),
            RevocationEntry("b" * 64, None, "Prepared", now, RevocationPhase.REVOKED),
        )
        rows = build_device_rows([], iter(entries))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.record.token == "" for row in rows))
        self.assertTrue(all(row.status() is LicenseStatus.REVOKED for row in rows))
        self.assertFalse(rows[0].awaiting_publication)
        self.assertTrue(rows[1].awaiting_publication)
