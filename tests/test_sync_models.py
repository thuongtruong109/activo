from __future__ import annotations

import unittest

from license_admin.domain import LicenseRecord
from license_admin.sync_models import build_sync_diff


class SyncDiffTests(unittest.TestCase):
    def test_replacement_diff_is_deterministic_and_case_insensitive(self) -> None:
        unchanged = LicenseRecord(hwid="AAA", token="same", username="Zulu")
        old = LicenseRecord(hwid="bbb", token="old", username="Old")
        removed = LicenseRecord(hwid="ccc", token="removed", username="Removed")
        updated = LicenseRecord(hwid="BBB", token="new", username="Updated")
        added = LicenseRecord(hwid="ddd", token="added", username="Added")

        diff = build_sync_diff(
            [unchanged, updated, added],
            [removed, old, unchanged],
        )

        self.assertEqual(diff.added, (added,))
        self.assertEqual(diff.updated, (updated,))
        self.assertEqual(diff.removed, (removed,))
        self.assertEqual(diff.unchanged, (unchanged,))
        self.assertTrue(diff.has_changes)

    def test_no_change_diff_reports_only_unchanged(self) -> None:
        record = LicenseRecord(hwid="abc", token="same", username="User")

        diff = build_sync_diff([record], [record])

        self.assertFalse(diff.has_changes)
        self.assertEqual(diff.unchanged, (record,))


if __name__ == "__main__":
    unittest.main()
