from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import unittest

from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import issue_license_until
from license_admin.privacy_policy import LICENSE_TOKEN_CLAIMS, PRIVACY_SECTIONS


class PrivacyDisclosureContractTests(unittest.TestCase):
    def test_disclosed_claims_match_the_real_signer_and_are_readable_without_a_key(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
        now = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
        token = issue_license_until(
            private_key,
            username="Khách hàng kiểm tra",
            hwid="A" * 64,
            expires_at=now + timedelta(days=30),
            issuer="test-issuer",
            audience="test-product",
            now=now,
        )
        header_part, payload_part, _ = token.split(".")
        # No decryption or verification key is needed to read these values.
        header = json.loads(base64.urlsafe_b64decode(header_part + "=" * (-len(header_part) % 4)))
        payload = json.loads(base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4)))
        self.assertEqual(set(payload), set(LICENSE_TOKEN_CLAIMS))
        self.assertEqual(payload["username"], "Khách hàng kiểm tra")
        self.assertEqual(payload["hwid"], "a" * 64)
        self.assertEqual(payload["iat"], int(now.timestamp()))
        self.assertEqual(payload["exp"], int((now + timedelta(days=30)).timestamp()))
        self.assertEqual(header["alg"], "RS256")
        self.assertEqual(set(header), {"alg", "typ", "kid"})
        for language in ("en", "vi"):
            notice = " ".join(paragraph for _, paragraph in PRIVACY_SECTIONS[language])
            for claim in payload:
                with self.subTest(language=language, claim=claim):
                    self.assertIn(f"{claim} (", notice)


if __name__ == "__main__":
    unittest.main()
