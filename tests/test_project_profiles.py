from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from issue_license import LicenseIssueError
from license_admin.settings import ProjectStore, normalize_project_id
from workspace_temp import workspace_temp_dir


class ProjectProfileTests(unittest.TestCase):
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
            self.assertEqual(document["schema_version"], 1)

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


if __name__ == "__main__":
    unittest.main()
