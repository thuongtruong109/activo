from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from issue_license import LicenseIssueError, issue_license
from license_admin.domain import (
    LicenseStatus,
    parse_signed_csv,
    records_digest,
    serialize_signed_csv,
    validate_record_signatures,
)
from license_admin.storage import LicenseRepository
from workspace_temp import workspace_temp_dir

TEST_ISSUER = "test-license-server"
TEST_AUDIENCE = "test-desktop"


class LicenseAdminDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_key = rsa.generate_private_key(
            public_exponent=65_537,
            key_size=2_048,
        )

    def _token(self, hwid: str, *, now: datetime, days: int = 365) -> str:
        return issue_license(
            self.private_key,
            username="Khách hàng A",
            hwid=hwid,
            days=days,
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            now=now,
        )

    def test_signed_csv_round_trip_exposes_admin_metadata(self) -> None:
        now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        hwid = "a" * 64
        record = parse_signed_csv(
            f"hwid,token\n{hwid},{self._token(hwid, now=now)}\n"
        )[0]

        self.assertEqual(record.username, "Khách hàng A")
        self.assertEqual(record.status(now), LicenseStatus.ACTIVE)
        self.assertEqual(record.remaining_days(now), 365)
        reparsed = parse_signed_csv(serialize_signed_csv([record]))
        self.assertEqual(reparsed, [record])
        self.assertEqual(records_digest(reparsed), records_digest([record]))

    def test_invalid_token_is_visible_instead_of_silently_dropped(self) -> None:
        record = parse_signed_csv(f"HWID,JWT Token\n{'b' * 64},not-a-token\n")[0]

        self.assertEqual(record.status(), LicenseStatus.INVALID)
        self.assertIn("compact JWT", record.parse_error or "")

    def test_signature_validation_flags_token_from_another_key(self) -> None:
        now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        hwid = "9" * 64
        record = parse_signed_csv(
            f"{hwid},{self._token(hwid, now=now)}\n"
        )[0]
        unrelated_key = rsa.generate_private_key(
            public_exponent=65_537,
            key_size=2_048,
        )
        unrelated_public = unrelated_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        checked = validate_record_signatures([record], unrelated_public)[0]

        self.assertEqual(checked.status(now), LicenseStatus.INVALID)
        self.assertIn("signature", (checked.parse_error or "").casefold())

    def test_duplicate_hwid_is_rejected(self) -> None:
        hwid = "c" * 64
        with self.assertRaisesRegex(LicenseIssueError, "duplicate HWID"):
            parse_signed_csv(f"{hwid},one.two.three\n{hwid},one.two.three\n")

    def test_expiring_and_expired_statuses(self) -> None:
        now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        expiring = parse_signed_csv(
            f"{('d' * 64)},{self._token('d' * 64, now=now, days=7)}\n"
        )[0]
        expired = parse_signed_csv(
            f"{('e' * 64)},{self._token('e' * 64, now=now, days=1)}\n"
        )[0]

        self.assertEqual(expiring.status(now), LicenseStatus.EXPIRING)
        self.assertEqual(
            expired.status(now + timedelta(days=2)),
            LicenseStatus.EXPIRED,
        )

    def test_repository_save_is_reloadable(self) -> None:
        now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
        hwid = "f" * 64
        records = parse_signed_csv(f"{hwid},{self._token(hwid, now=now)}\n")
        with workspace_temp_dir() as directory:
            repository = LicenseRepository(Path(directory) / "licenses.csv")
            repository.save(records)
            self.assertEqual(repository.load(), records)


if __name__ == "__main__":
    unittest.main()
