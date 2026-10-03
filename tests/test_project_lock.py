from __future__ import annotations

from pathlib import Path
import unittest

from issue_license import LicenseIssueError
from license_admin.project_lock import LOCK_FILENAME, ProjectLease
from workspace_temp import workspace_temp_dir


class ProjectLeaseTests(unittest.TestCase):
    def test_same_project_allows_only_one_live_writer(self) -> None:
        with workspace_temp_dir() as directory:
            project = Path(directory) / "project"
            first = ProjectLease.acquire(project)
            try:
                self.assertTrue(first.held)
                self.assertTrue((project / LOCK_FILENAME).exists())
                with self.assertRaisesRegex(LicenseIssueError, "already open"):
                    ProjectLease.acquire(project)
            finally:
                first.release()

            self.assertFalse((project / LOCK_FILENAME).exists())
            replacement = ProjectLease.acquire(project)
            replacement.release()
            replacement.release()

    def test_different_projects_can_be_leased_together(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            first = ProjectLease.acquire(root / "first")
            second = ProjectLease.acquire(root / "second")
            try:
                self.assertTrue(first.held)
                self.assertTrue(second.held)
            finally:
                second.release()
                first.release()

    def test_context_manager_releases_after_exception(self) -> None:
        with workspace_temp_dir() as directory:
            project = Path(directory) / "project"
            with self.assertRaisesRegex(RuntimeError, "boom"):
                with ProjectLease.acquire(project):
                    raise RuntimeError("boom")

            replacement = ProjectLease.acquire(project)
            replacement.release()


if __name__ == "__main__":
    unittest.main()
