from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from issue_license import LicenseIssueError
from license_admin.project_config import (
    export_project_config,
    import_project_config,
)
from license_admin.settings import ProjectStore
from workspace_temp import workspace_temp_dir


class ProjectConfigTests(unittest.TestCase):
    def test_round_trip_updates_settings_but_preserves_project_assets(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store = ProjectStore(root / "projects")
            alpha = store.create("Alpha")
            source = replace(
                alpha,
                project_name="Portable name",
                spreadsheet_id="a" * 24,
                worksheet="Licenses",
                public_csv_url="https://example.test/licenses.csv",
                issuer="portable-issuer",
                audience="portable-audience",
            )
            exported = export_project_config(source, root / "settings.json")
            beta = store.create("Beta")

            imported = import_project_config(exported, beta)

            self.assertEqual(imported.project_id, "beta")
            self.assertEqual(imported.project_name, "Portable name")
            self.assertEqual(imported.spreadsheet_id, "a" * 24)
            self.assertEqual(imported.signing_key_path, beta.signing_key_path)
            self.assertEqual(imported.public_key_path, beta.public_key_path)
            self.assertEqual(imported.local_csv_path, beta.local_csv_path)
            self.assertEqual(imported.service_account_path, beta.service_account_path)
            document = json.loads(exported.read_text(encoding="utf-8"))
            self.assertNotIn("private_key", document["project"])
            self.assertNotIn("service_account", document["project"])

    def test_existing_project_json_can_supply_portable_settings(self) -> None:
        with workspace_temp_dir() as directory:
            store = ProjectStore(Path(directory) / "projects")
            source = store.create("Source")
            target = store.create("Target")

            imported = import_project_config(store.profile_path("source"), target)

            self.assertEqual(imported.project_id, "target")
            self.assertEqual(imported.project_name, source.project_name)
            self.assertEqual(imported.issuer, source.issuer)

    def test_invalid_schema_and_insecure_url_are_rejected(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store = ProjectStore(root / "projects")
            current = store.create("Target")
            invalid_schema = root / "invalid-schema.json"
            invalid_schema.write_text(
                json.dumps({"schema_version": 99, "project": {}}),
                encoding="utf-8",
            )
            insecure = root / "insecure.json"
            insecure.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "project": {
                            "name": "Target",
                            "issuer": "issuer",
                            "audience": "audience",
                            "public_csv_url": "http://example.test/licenses.csv",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(LicenseIssueError, "schema version"):
                import_project_config(invalid_schema, current)
            with self.assertRaisesRegex(LicenseIssueError, "HTTPS"):
                import_project_config(insecure, current)


if __name__ == "__main__":
    unittest.main()
