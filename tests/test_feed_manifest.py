from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError, issue_license
from license_admin.domain import parse_signed_csv
from license_admin.feed_manifest import (
    FeedDocument,
    FeedTombstone,
    ManifestRevisionStore,
    parse_feed_csv,
    parse_verify_and_accept_feed,
    publication_content_digest,
    serialize_feed_csv,
    sign_feed,
    verify_feed,
)
from workspace_temp import workspace_temp_dir


class FeedManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.private_key = rsa.generate_private_key(
            public_exponent=65_537,
            key_size=2_048,
        )
        self.public_pem = self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)

    def _record(self, character: str = "a"):
        hwid = character * 64
        token = issue_license(
            self.private_key,
            username="Manifest User",
            hwid=hwid,
            days=365,
            issuer="issuer",
            audience="audience",
            now=self.now,
        )
        return parse_signed_csv(f"{hwid},{token}\n")[0]

    def test_signed_feed_round_trip_binds_manifest_and_tombstones(self) -> None:
        record = self._record("a")
        tombstone = FeedTombstone("b" * 64, "c" * 32, self.now)
        signed = sign_feed(
            [record],
            [tombstone],
            self.private_key,
            revision=7,
            issuer="issuer",
            audience="audience",
            generated_at=self.now,
        )

        parsed = parse_feed_csv(serialize_feed_csv(signed))
        verified = verify_feed(
            parsed,
            self.public_pem,
            expected_issuer="issuer",
            expected_audience="audience",
            minimum_revision=7,
            now=self.now + timedelta(hours=1),
        )

        self.assertEqual(verified.records, (record,))
        self.assertEqual(verified.tombstones, (tombstone,))
        self.assertIsNotNone(verified.manifest)
        self.assertEqual(verified.manifest.revision if verified.manifest else None, 7)
        self.assertTrue(verified.is_revoked(hwid="b" * 64))
        self.assertTrue(verified.is_revoked(hwid="d" * 64, jti="c" * 32))
        self.assertFalse(verified.is_revoked(hwid="d" * 64, jti="e" * 32))

    def test_tampered_tombstone_is_rejected_by_signed_digest(self) -> None:
        signed = sign_feed(
            [self._record("a")],
            [FeedTombstone("b" * 64, None, self.now)],
            self.private_key,
            revision=1,
            issuer="issuer",
            audience="audience",
            generated_at=self.now,
        )
        tampered = FeedDocument(
            signed.records,
            (FeedTombstone("c" * 64, None, self.now),),
            signed.manifest_token,
        )

        with self.assertRaisesRegex(LicenseIssueError, "does not match"):
            verify_feed(
                tampered,
                self.public_pem,
                expected_issuer="issuer",
                expected_audience="audience",
                now=self.now,
            )

    def test_active_jti_column_must_match_the_signed_token(self) -> None:
        signed = sign_feed(
            [self._record("a")],
            [],
            self.private_key,
            revision=1,
            issuer="issuer",
            audience="audience",
            generated_at=self.now,
        )
        rows = list(csv.reader(io.StringIO(serialize_feed_csv(signed))))
        rows[2][3] = ""
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerows(rows)

        with self.assertRaisesRegex(LicenseIssueError, "mismatched JTI"):
            parse_feed_csv(output.getvalue())

    def test_active_jti_cannot_also_be_revoked(self) -> None:
        record = self._record("a")
        assert record.jti is not None

        with self.assertRaisesRegex(LicenseIssueError, "active JTI"):
            sign_feed(
                [record],
                [FeedTombstone("b" * 64, record.jti, self.now)],
                self.private_key,
                revision=1,
                issuer="issuer",
                audience="audience",
                generated_at=self.now,
            )

    def test_client_rejects_stale_and_rolled_back_manifests(self) -> None:
        record = self._record("a")
        revision_two = sign_feed(
            [record],
            [],
            self.private_key,
            revision=2,
            issuer="issuer",
            audience="audience",
            generated_at=self.now,
            freshness=timedelta(hours=1),
        )
        revision_one = sign_feed(
            [record],
            [],
            self.private_key,
            revision=1,
            issuer="issuer",
            audience="audience",
            generated_at=self.now,
            freshness=timedelta(hours=1),
        )
        with workspace_temp_dir() as directory:
            store = ManifestRevisionStore(Path(directory) / "accepted.json")
            parse_verify_and_accept_feed(
                serialize_feed_csv(revision_two),
                self.public_pem,
                issuer="issuer",
                audience="audience",
                revision_store=store,
                now=self.now + timedelta(minutes=30),
            )

            with self.assertRaisesRegex(LicenseIssueError, "rollback"):
                parse_verify_and_accept_feed(
                    serialize_feed_csv(revision_one),
                    self.public_pem,
                    issuer="issuer",
                    audience="audience",
                    revision_store=store,
                    now=self.now + timedelta(minutes=30),
                )
            with self.assertRaisesRegex(LicenseIssueError, "stale"):
                verify_feed(
                    revision_two,
                    self.public_pem,
                    expected_issuer="issuer",
                    expected_audience="audience",
                    now=self.now + timedelta(hours=2),
                )

    def test_client_rejects_same_revision_with_different_content(self) -> None:
        first = sign_feed(
            [self._record("a")],
            [],
            self.private_key,
            revision=3,
            issuer="issuer",
            audience="audience",
            generated_at=self.now,
        )
        second = sign_feed(
            [self._record("b")],
            [],
            self.private_key,
            revision=3,
            issuer="issuer",
            audience="audience",
            generated_at=self.now,
        )
        with workspace_temp_dir() as directory:
            store = ManifestRevisionStore(Path(directory) / "accepted.json")
            assert first.manifest is not None
            assert second.manifest is not None
            store.accept(
                first.manifest,
                publication_content_digest(first.records, first.tombstones),
            )

            with self.assertRaisesRegex(LicenseIssueError, "equivocation"):
                store.accept(
                    second.manifest,
                    publication_content_digest(second.records, second.tombstones),
                )

    def test_legacy_revision_floor_is_upgraded_with_a_content_digest(self) -> None:
        first = sign_feed(
            [self._record("a")],
            [],
            self.private_key,
            revision=3,
            issuer="issuer",
            audience="audience",
            generated_at=self.now,
        )
        second = sign_feed(
            [self._record("b")],
            [],
            self.private_key,
            revision=3,
            issuer="issuer",
            audience="audience",
            generated_at=self.now,
        )
        assert first.manifest is not None
        assert second.manifest is not None
        with workspace_temp_dir() as directory:
            path = Path(directory) / "accepted.json"
            store = ManifestRevisionStore(path)
            identity = store._identity("issuer", "audience")
            path.write_text(json.dumps({identity: 3}), encoding="utf-8")
            store.accept(
                first.manifest,
                publication_content_digest(first.records, first.tombstones),
            )

            with self.assertRaisesRegex(LicenseIssueError, "equivocation"):
                store.accept(
                    second.manifest,
                    publication_content_digest(second.records, second.tombstones),
                )

    def test_legacy_csv_is_not_accepted_as_secure_feed_by_default(self) -> None:
        record = self._record("a")
        legacy = f"hwid,token\n{record.hwid},{record.token}\n"

        with self.assertRaisesRegex(LicenseIssueError, "v2 header"):
            parse_feed_csv(legacy)
        parsed = parse_feed_csv(legacy, allow_legacy=True)
        self.assertEqual(parsed.records, (record,))
        self.assertEqual(parsed.manifest_token, "")


if __name__ == "__main__":
    unittest.main()
