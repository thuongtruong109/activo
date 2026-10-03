from __future__ import annotations

import json
from pathlib import Path
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError
from license_admin.key_identity import KeyIdentityStore
from workspace_temp import workspace_temp_dir


def _write_public_key(path: Path) -> Path:
    key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


class KeyIdentityTests(unittest.TestCase):
    def test_rotation_tracks_identity_timestamps_and_trusted_history(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            first_path = _write_public_key(root / "keys" / "first.pem")
            second_path = _write_public_key(root / "keys" / "second.pem")
            store = KeyIdentityStore(root)

            first_ring = store.reconcile_active(first_path)
            first = first_ring.active
            self.assertIsNotNone(first)
            assert first is not None
            self.assertIsNone(first.rotated_at)
            self.assertIsNone(first.revoked_at)
            self.assertTrue(first.created_at.endswith("Z"))

            second_ring = store.reconcile_active(second_path)
            second = second_ring.active
            self.assertIsNotNone(second)
            assert second is not None
            rotated = next(key for key in second_ring.keys if key.key_id == first.key_id)
            self.assertIsNotNone(rotated.rotated_at)
            self.assertEqual(
                store.trusted_public_key_paths(),
                (second_path.resolve(), first_path.resolve()),
            )

            revoked_ring = store.revoke(first.key_id)
            revoked = next(key for key in revoked_ring.keys if key.key_id == first.key_id)
            self.assertIsNotNone(revoked.revoked_at)
            self.assertEqual(store.trusted_public_key_paths(), (second_path.resolve(),))
            with self.assertRaisesRegex(LicenseIssueError, "Rotate away"):
                store.revoke(second.key_id)

            document = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertEqual(document["active_key_id"], second.key_id)
            self.assertIn("created_at", document["keys"][0])
            self.assertIn("rotated_at", document["keys"][0])
            self.assertIn("revoked_at", document["keys"][0])


if __name__ == "__main__":
    unittest.main()

