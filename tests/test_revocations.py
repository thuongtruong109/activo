from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest

from license_admin.domain import LicenseRecord
from license_admin.revocations import (
    RevocationPhase,
    RevocationRepository,
    mark_published,
    mark_revoked,
    request_revocation,
)
from workspace_temp import workspace_temp_dir


class RevocationTests(unittest.TestCase):
    def test_lifecycle_is_pending_then_revoked_then_published(self) -> None:
        now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        record = LicenseRecord(
            hwid="a" * 64,
            token="token",
            username="User",
            jti="b" * 32,
        )

        pending = request_revocation((), record, now=now)
        revoked = mark_revoked(pending)
        published = mark_published(revoked, revision=4, published_at=now)

        self.assertEqual(pending[0].phase, RevocationPhase.PENDING)
        self.assertEqual(revoked[0].phase, RevocationPhase.REVOKED)
        self.assertIsNone(revoked[0].published_at)
        self.assertEqual(published[0].phase, RevocationPhase.PUBLISHED)
        self.assertEqual(published[0].published_revision, 4)

    def test_repository_round_trip_preserves_publication_metadata(self) -> None:
        now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        record = LicenseRecord(
            hwid="a" * 64,
            token="token",
            username="User",
            jti="b" * 32,
        )
        published = mark_published(
            mark_revoked(request_revocation((), record, now=now)),
            revision=9,
            published_at=now,
        )
        with workspace_temp_dir() as directory:
            repository = RevocationRepository(Path(directory) / "revocations.json")

            repository.save(published)

            self.assertEqual(repository.load(), published)


if __name__ == "__main__":
    unittest.main()
