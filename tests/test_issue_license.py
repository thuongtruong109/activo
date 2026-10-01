from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError, issue_license, normalize_hwid
from license_admin.domain import inspect_license

TEST_ISSUER = "test-license-server"
TEST_AUDIENCE = "test-desktop"


class IssueLicenseTests(unittest.TestCase):
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

    def test_issued_token_round_trips_through_client_verifier(self) -> None:
        now = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
        hwid = "A" * 64

        token = issue_license(
            self.private_key,
            username="Khách hàng",
            hwid=hwid,
            days=365,
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            now=now,
        )
        record = inspect_license(
            hwid,
            token,
            public_key_pem=self.public_key,
            expected_issuer=TEST_ISSUER,
            expected_audience=TEST_AUDIENCE,
        )

        self.assertIsNone(record.parse_error)
        self.assertEqual(record.username, "Khách hàng")
        self.assertEqual(record.hwid, hwid.casefold())
        self.assertEqual(record.expires_at, now + timedelta(days=365))

    def test_rejects_bad_hwid_duration_and_username(self) -> None:
        with self.assertRaisesRegex(LicenseIssueError, "64 hexadecimal"):
            normalize_hwid("not-a-hwid")
        with self.assertRaisesRegex(LicenseIssueError, "between 1"):
            issue_license(
                self.private_key,
                username="alice",
                hwid="a" * 64,
                days=0,
                issuer=TEST_ISSUER,
                audience=TEST_AUDIENCE,
            )
        with self.assertRaisesRegex(LicenseIssueError, "control"):
            issue_license(
                self.private_key,
                username="alice\nadmin",
                hwid="a" * 64,
                days=30,
                issuer=TEST_ISSUER,
                audience=TEST_AUDIENCE,
            )


if __name__ == "__main__":
    unittest.main()
