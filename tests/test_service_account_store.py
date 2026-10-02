from __future__ import annotations

import json
from pathlib import Path
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError
from license_admin.service_account_store import (
    import_service_account,
    inspect_service_account,
    load_service_account,
)
from workspace_temp import workspace_temp_dir


def write_service_account(path: Path, *, email: str) -> Path:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    document = {
        "type": "service_account",
        "project_id": "example-project",
        "private_key_id": "key-id",
        "private_key": private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii"),
        "client_email": email,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class ServiceAccountStoreTests(unittest.TestCase):
    def test_valid_service_account_is_inspected_and_loaded(self) -> None:
        with workspace_temp_dir() as directory:
            source = write_service_account(
                Path(directory) / "google.json",
                email="publisher@example-project.iam.gserviceaccount.com",
            )

            info = inspect_service_account(source)
            document = load_service_account(source)

            self.assertEqual(info.project_id, "example-project")
            self.assertEqual(info.client_email, document["client_email"])

    def test_import_copies_credential_into_only_selected_project(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            source = write_service_account(
                root / "source.json",
                email="alpha@example-project.iam.gserviceaccount.com",
            )

            imported = import_service_account(source, root / "projects" / "alpha")

            self.assertEqual(imported.path.name, "service-account.json")
            self.assertTrue(imported.path.is_file())
            self.assertFalse(
                (root / "projects" / "beta" / "service-account.json").exists()
            )

    def test_existing_credential_requires_explicit_overwrite(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            first = write_service_account(
                root / "first.json",
                email="first@example-project.iam.gserviceaccount.com",
            )
            second = write_service_account(
                root / "second.json",
                email="second@example-project.iam.gserviceaccount.com",
            )
            destination = root / "projects" / "alpha"
            original = import_service_account(first, destination)

            with self.assertRaisesRegex(LicenseIssueError, "Confirm replacement"):
                import_service_account(second, destination)

            self.assertEqual(
                inspect_service_account(original.path).client_email,
                "first@example-project.iam.gserviceaccount.com",
            )
            replacement = import_service_account(
                second,
                destination,
                overwrite=True,
            )
            self.assertEqual(
                inspect_service_account(replacement.path).client_email,
                "second@example-project.iam.gserviceaccount.com",
            )

    def test_non_service_account_json_is_rejected(self) -> None:
        with workspace_temp_dir() as directory:
            source = Path(directory) / "oauth-client.json"
            source.write_text(
                json.dumps({"type": "authorized_user", "client_email": "x"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(LicenseIssueError, "service_account"):
                inspect_service_account(source)


if __name__ == "__main__":
    unittest.main()
