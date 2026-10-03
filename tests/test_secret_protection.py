from __future__ import annotations

import os
import unittest

from issue_license import LicenseIssueError
from license_admin.secret_protection import (
    is_protected_secret,
    protect_secret,
    unprotect_secret,
)


class SecretProtectionTests(unittest.TestCase):
    def test_current_user_round_trip(self) -> None:
        secret = b"private-key-material"

        protected = protect_secret(secret)

        if os.name == "nt":
            self.assertTrue(is_protected_secret(protected))
            self.assertNotIn(secret, protected)
        self.assertEqual(unprotect_secret(protected), secret)

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-specific")
    def test_corrupted_dpapi_envelope_fails_closed(self) -> None:
        protected = bytearray(protect_secret(b"private-key-material"))
        protected[-1] ^= 0xFF

        with self.assertRaises(LicenseIssueError):
            unprotect_secret(bytes(protected))


if __name__ == "__main__":
    unittest.main()

