from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError
from license_admin.secret_protection import is_protected_secret
from license_admin.settings import ProjectStore, normalize_project_id
from workspace_temp import workspace_temp_dir


class ProjectProfileTests(unittest.TestCase):
    @staticmethod
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

    @staticmethod
    def _write_legacy_profile(project_directory: Path) -> Path:
        project_directory.mkdir(parents=True, exist_ok=True)
        profile_path = project_directory / "project.json"
        profile_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": project_directory.name,
                    "name": "Legacy Project",
                    "private_key": "private.pem",
                    "public_key": "public.pem",
                    "issuer": "legacy-issuer",
                    "audience": "legacy-audience",
                }
            ),
            encoding="utf-8",
        )
        return profile_path

    def test_profiles_are_isolated_and_round_trip_relative_paths(self) -> None:
        with workspace_temp_dir() as directory:
            store = ProjectStore(Path(directory) / "projects")
            default_profile = store.ensure_default()
            second = store.create("Ứng dụng Ảnh")
            second = replace(
                second,
                spreadsheet_id="a" * 24,
                public_csv_url="https://example.test/licenses.csv",
            )
            store.save(second)

            loaded = store.load("ung-dung-anh")

            self.assertEqual(default_profile.project_id, "default")
            self.assertEqual(loaded.project_name, "Ứng dụng Ảnh")
            self.assertEqual(
                loaded.local_csv_path.parent,
                Path(directory) / "projects" / "ung-dung-anh",
            )
            self.assertEqual(loaded.spreadsheet_id, "a" * 24)
            self.assertEqual(len(store.list_profiles()), 2)
            self.assertEqual(
                store.project_directory(loaded.project_id),
                Path(directory) / "projects" / "ung-dung-anh",
            )
            document = json.loads(store.profile_path(loaded.project_id).read_text())
            self.assertEqual(document["schema_version"], 2)
            profile_backups = list(
                (
                    store.profile_path(loaded.project_id).parent
                    / ".backups"
                    / "project.json"
                ).glob("*.bak")
            )
            self.assertEqual(len(profile_backups), 1)

    def test_duplicate_or_invalid_project_id_is_rejected(self) -> None:
        with workspace_temp_dir() as directory:
            store = ProjectStore(Path(directory) / "projects")
            store.create("Project One")

            with self.assertRaisesRegex(LicenseIssueError, "already exists"):
                store.create("Project One")
            with self.assertRaises(LicenseIssueError):
                normalize_project_id("---")

    def test_unsupported_profile_schema_is_rejected(self) -> None:
        with workspace_temp_dir() as directory:
            store = ProjectStore(Path(directory) / "projects")
            profile = store.ensure_default()
            profile_path = store.profile_path(profile.project_id)
            document = json.loads(profile_path.read_text())
            document["schema_version"] = 99
            profile_path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(LicenseIssueError, "schema version"):
                store.load(profile.project_id)

    def test_corrupted_profile_is_isolated_from_valid_profiles(self) -> None:
        with workspace_temp_dir() as directory:
            store = ProjectStore(Path(directory) / "projects")
            valid = store.create("Valid Project")
            broken_path = store.profile_path("broken")
            broken_path.parent.mkdir(parents=True)
            broken_path.write_text("{not-json", encoding="utf-8")

            scan = store.scan_profiles()

            self.assertEqual(
                [profile.project_id for profile in scan.profiles],
                [valid.project_id],
            )
            self.assertEqual([issue.project_id for issue in scan.issues], ["broken"])
            self.assertEqual(store.ensure_default().project_id, valid.project_id)

    def test_corrupted_default_profile_is_never_overwritten(self) -> None:
        with workspace_temp_dir() as directory:
            store = ProjectStore(Path(directory) / "projects")
            broken_path = store.profile_path("default")
            broken_path.parent.mkdir(parents=True)
            broken_content = "{not-json"
            broken_path.write_text(broken_content, encoding="utf-8")

            recovered_default = store.ensure_default()

            self.assertEqual(recovered_default.project_id, "default-2")
            self.assertEqual(broken_path.read_text(encoding="utf-8"), broken_content)
            self.assertTrue(store.profile_path("default-2").is_file())

    def test_schema_one_private_pem_migrates_only_after_profile_save(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            project_directory = root / "projects" / "legacy"
            profile_path = self._write_legacy_profile(project_directory)
            legacy_private = project_directory / "private.pem"
            legacy_private.write_bytes(b"legacy-private-material")
            store = ProjectStore(root / "projects")

            with patch("license_admin.key_store.restrict_to_current_user"):
                loaded = store.load("legacy")

            protected_private = project_directory / "private.key"
            self.assertEqual(loaded.signing_key_path, protected_private)
            self.assertEqual(
                is_protected_secret(protected_private.read_bytes()),
                os.name == "nt",
            )
            self.assertFalse(legacy_private.exists())
            document = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(document["schema_version"], 2)
            self.assertEqual(document["private_key"], "private.key")

    def test_schema_one_migration_rolls_back_if_profile_save_fails(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            project_directory = root / "projects" / "legacy"
            profile_path = self._write_legacy_profile(project_directory)
            original_profile = profile_path.read_bytes()
            legacy_private = project_directory / "private.pem"
            legacy_private.write_bytes(b"legacy-private-material")
            store = ProjectStore(root / "projects")

            with (
                patch("license_admin.key_store.restrict_to_current_user"),
                patch.object(
                    store,
                    "save",
                    side_effect=LicenseIssueError("simulated profile failure"),
                ),
                self.assertRaisesRegex(LicenseIssueError, "simulated profile failure"),
            ):
                store.load("legacy")

            self.assertTrue(legacy_private.is_file())
            self.assertFalse((project_directory / "private.key").exists())
            self.assertEqual(profile_path.read_bytes(), original_profile)

    def test_profile_save_failure_restores_key_identity_metadata(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store = ProjectStore(root / "projects")
            profile = store.ensure_default()
            first_public = self._write_public_key(root / "keys" / "first.pem")
            configured = replace(profile, public_key_path=first_public)
            store.save(configured)
            profile_path = store.profile_path(profile.project_id)
            keyring_path = profile_path.parent / "keyring.json"
            original_profile = profile_path.read_bytes()
            original_keyring = keyring_path.read_bytes()
            second_public = self._write_public_key(root / "keys" / "second.pem")

            with (
                patch(
                    "license_admin.settings.atomic_write_text",
                    side_effect=OSError("simulated profile failure"),
                ),
                self.assertRaisesRegex(LicenseIssueError, "simulated profile failure"),
            ):
                store.save(replace(configured, public_key_path=second_public))

            self.assertEqual(profile_path.read_bytes(), original_profile)
            self.assertEqual(keyring_path.read_bytes(), original_keyring)


if __name__ == "__main__":
    unittest.main()
