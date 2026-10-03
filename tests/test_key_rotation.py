from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import issue_license
from license_admin.domain import LicenseRecord, parse_signed_csv
from license_admin.key_rotation import resign_unexpired_records


class KeyRotationTests(unittest.TestCase):
    def test_resign_migrates_unexpired_and_preserves_expired_or_invalid_rows(self) -> None:
        now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        old_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
        new_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
        active_hwid = "a" * 64
        expired_hwid = "b" * 64
        active = parse_signed_csv(
            f"{active_hwid},{issue_license(old_key, username='Active', hwid=active_hwid, days=30, issuer='issuer', audience='audience', now=now)}\n"
        )[0]
        expired = LicenseRecord(
            hwid=expired_hwid,
            token="historic-token",
            username="Expired",
            expires_at=now - timedelta(days=1),
        )
        invalid = LicenseRecord(
            hwid="c" * 64,
            token="invalid",
            parse_error="invalid",
        )

        result = resign_unexpired_records(
            [active, expired, invalid],
            new_key,
            issuer="issuer",
            audience="audience",
            now=now + timedelta(minutes=1),
        )

        self.assertEqual(result.resigned_count, 1)
        self.assertEqual(result.unchanged_count, 2)
        self.assertNotEqual(result.records[0].token, active.token)
        self.assertIsNone(result.records[0].parse_error)
        self.assertIs(result.records[1], expired)
        self.assertIs(result.records[2], invalid)


if __name__ == "__main__":
    unittest.main()

