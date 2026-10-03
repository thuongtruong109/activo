from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from issue_license import LicenseIssueError
from license_admin.windows_security import restrict_tree_to_current_user
from workspace_temp import workspace_temp_dir


class WindowsSecurityTests(unittest.TestCase):
    def test_tree_restriction_covers_files_directories_and_root(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory) / "project"
            nested = root / "nested"
            nested.mkdir(parents=True)
            secret = nested / "private.key"
            secret.write_bytes(b"secret")

            with patch(
                "license_admin.windows_security.restrict_to_current_user"
            ) as restrict:
                restrict_tree_to_current_user(root)

            restricted = {call.args[0] for call in restrict.call_args_list}
            self.assertEqual(restricted, {root, nested, secret})

    def test_tree_restriction_refuses_links(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            outside = Path(directory) / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            link = root / "linked.txt"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"Symbolic links are unavailable: {exc}")

            with (
                patch("license_admin.windows_security.restrict_to_current_user"),
                self.assertRaisesRegex(LicenseIssueError, "through a link"),
            ):
                restrict_tree_to_current_user(root)


if __name__ == "__main__":
    unittest.main()
