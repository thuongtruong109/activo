from __future__ import annotations

from datetime import datetime, timezone
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError
from license_admin.domain import inspect_license, parse_signed_csv
from migrate_license_csv import migrate_legacy_csv

TEST_ISSUER = "test-license-server"
TEST_AUDIENCE = "test-desktop"


class MigrateLicenseCsvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_key = rsa.generate_private_key(
            public_exponent=65_537,
            key_size=2_048,
        )
        cls.public_key = cls.private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def test_migrates_active_rows_and_skips_expired_rows(self) -> None:
        active_hwid = "a" * 64
        expired_hwid = "b" * 64
        legacy = (
            "username,hwid,expired\n"
            f'"Khách, hàng",{active_hwid},08/15/2026\n'
            f"old,{expired_hwid},08/13/2026\n"
        )
        now = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)

        result = migrate_legacy_csv(
            legacy,
            self.private_key,
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            now=now,
        )

        self.assertEqual(result.issued_count, 1)
        self.assertEqual(result.skipped_expired_count, 1)
        records = parse_signed_csv(result.csv_text)
        self.assertEqual([record.hwid for record in records], [active_hwid])
        record = inspect_license(
            active_hwid,
            records[0].token,
            public_key_pem=self.public_key,
            expected_issuer=TEST_ISSUER,
            expected_audience=TEST_AUDIENCE,
        )
        self.assertIsNone(record.parse_error)
        self.assertEqual(record.username, "Khách, hàng")
        self.assertEqual(
            record.expires_at,
            datetime(2026, 8, 15, 23, 59, 59, tzinfo=timezone.utc),
        )

    def test_rejects_duplicate_hwid_and_bad_expiry(self) -> None:
        hwid = "c" * 64
        with self.assertRaisesRegex(LicenseIssueError, "duplicate"):
            migrate_legacy_csv(
                f"alice,{hwid},08/15/2026\nbob,{hwid},08/16/2026\n",
                self.private_key,
                issuer=TEST_ISSUER,
                audience=TEST_AUDIENCE,
                now=datetime(2026, 8, 14, tzinfo=timezone.utc),
            )
        with self.assertRaisesRegex(LicenseIssueError, "invalid expiry"):
            migrate_legacy_csv(
                f"alice,{hwid},tomorrow\n",
                self.private_key,
                issuer=TEST_ISSUER,
                audience=TEST_AUDIENCE,
                now=datetime(2026, 8, 14, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
