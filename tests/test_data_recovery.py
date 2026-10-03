from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import issue_license
from license_admin.data_recovery import ProjectDataState, load_project_records
from license_admin.domain import parse_signed_csv
from license_admin.settings import ProjectStore
from license_admin.storage import LicenseRepository
from workspace_temp import workspace_temp_dir


class ProjectDataRecoveryTests(unittest.TestCase):
    def test_missing_data_is_empty_and_writable_without_a_key(self) -> None:
        with workspace_temp_dir() as directory:
            settings = ProjectStore(Path(directory) / "projects").ensure_default()

            result = load_project_records(settings)

            self.assertEqual(result.state, ProjectDataState.EMPTY)
            self.assertTrue(result.state.allows_writes)
            self.assertEqual(result.records, ())

    def test_wrong_public_key_enters_read_only_recovery(self) -> None:
        with workspace_temp_dir() as directory:
            settings = ProjectStore(Path(directory) / "projects").ensure_default()
            signing_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
            wrong_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
            settings.public_key_path.write_bytes(
                wrong_key.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )
            hwid = "a" * 64
            token = issue_license(
                signing_key,
                username="Test user",
                hwid=hwid,
                days=30,
                issuer=settings.issuer,
                audience=settings.audience,
                now=datetime(2026, 10, 3, tzinfo=timezone.utc),
            )
            LicenseRepository(settings.local_csv_path).save(
                parse_signed_csv(f"hwid,token\n{hwid},{token}\n")
            )

            result = load_project_records(settings)

            self.assertEqual(result.state, ProjectDataState.WRONG_KEY)
            self.assertFalse(result.state.allows_writes)
            self.assertEqual(len(result.records), 1)

    def test_permission_error_enters_read_only_recovery(self) -> None:
        with workspace_temp_dir() as directory:
            settings = ProjectStore(Path(directory) / "projects").ensure_default()
            settings.local_csv_path.write_text("hwid,token\n", encoding="utf-8")
            original_read_text = Path.read_text

            def denied(path: Path, *args: object, **kwargs: object) -> str:
                if path == settings.local_csv_path:
                    raise PermissionError("denied for test")
                return original_read_text(path, *args, **kwargs)

            with patch.object(Path, "read_text", denied):
                result = load_project_records(settings)

            self.assertEqual(result.state, ProjectDataState.PERMISSION_DENIED)
            self.assertFalse(result.state.allows_writes)

    def test_non_file_data_path_is_unavailable_not_empty(self) -> None:
        with workspace_temp_dir() as directory:
            settings = ProjectStore(Path(directory) / "projects").ensure_default()
            data_directory = Path(directory) / "not-a-csv"
            data_directory.mkdir()

            result = load_project_records(
                replace(settings, local_csv_path=data_directory)
            )

            self.assertEqual(result.state, ProjectDataState.UNAVAILABLE)
            self.assertFalse(result.state.allows_writes)


if __name__ == "__main__":
    unittest.main()
