from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from issue_license import LicenseIssueError
from license_admin.app_data import application_data_root, migrate_legacy_projects
from workspace_temp import workspace_temp_dir


class AppDataTests(unittest.TestCase):
    def test_windows_default_is_under_local_app_data(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows-specific path assertion")
        expected = Path(os.environ["LOCALAPPDATA"]) / "Activo" / "LicenseAdmin"
        self.assertEqual(application_data_root(), expected)

    def test_legacy_projects_are_copied_only_when_destination_is_absent(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            legacy = root / "legacy-projects"
            profile = legacy / "alpha" / "project.json"
            profile.parent.mkdir(parents=True)
            profile.write_text("{}", encoding="utf-8")
            destination = root / "local-app-data" / "projects"

            with (
                patch("license_admin.app_data.restrict_to_current_user"),
                patch("license_admin.app_data.restrict_tree_to_current_user"),
            ):
                migrated = migrate_legacy_projects(legacy, destination)
                repeated = migrate_legacy_projects(legacy, destination)

            self.assertTrue(migrated)
            self.assertFalse(repeated)
            self.assertEqual(
                (destination / "alpha" / "project.json").read_text(encoding="utf-8"),
                "{}",
            )
            self.assertTrue(profile.is_file())

    def test_existing_empty_destination_blocks_ambiguous_migration(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            legacy = root / "legacy-projects"
            profile = legacy / "alpha" / "project.json"
            profile.parent.mkdir(parents=True)
            profile.write_text("{}", encoding="utf-8")
            destination = root / "local-app-data" / "projects"
            destination.mkdir(parents=True)

            with (
                patch("license_admin.app_data.restrict_to_current_user"),
                patch("license_admin.app_data.restrict_tree_to_current_user") as secure,
                self.assertRaisesRegex(LicenseIssueError, "contains no profiles"),
            ):
                migrate_legacy_projects(legacy, destination)

            self.assertEqual(secure.call_count, 2)
            self.assertTrue(profile.is_file())
            self.assertEqual(list(destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

