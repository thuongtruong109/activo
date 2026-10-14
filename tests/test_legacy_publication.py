from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import csv
import io
import unittest

from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError, issue_license
from license_admin.domain import parse_signed_csv
from license_admin.feed_format import LEGACY, parse_publication_csv, publication_digest, serialize_legacy_feed
from license_admin.feed_manifest import FeedDocument, FeedTombstone, feed_digest, sign_feed
from license_admin.google_sheets import GoogleSheetsClient, GoogleSheetsConfig, RemoteRevision, SheetConflictError
from license_admin.sheet_presentation import sheet_format_requests
from license_admin.revocations import (
    RevocationPhase, mark_published, mark_revoked, request_device_removal, request_revocation,
    RevocationRepository,
)
from test_license_admin_google_sheets import ProtocolSheetsClient
from license_admin.settings import ProjectStore
from workspace_temp import workspace_temp_dir
from pathlib import Path


class LegacyProtocolClient(ProtocolSheetsClient):
    def __init__(self, existing=()):
        super().__init__(list(existing))
        self.config = replace(self.config, feed_format=LEGACY)
        self.current = replace(self.current, digest=publication_digest(FeedDocument(tuple(existing), ())))

    def _publish_batch(self, **kwargs):
        super()._publish_batch(**kwargs)
        self.current = replace(self.current, disabled_hwids=self.stage_feed.disabled_hwids,
                               content_digest=publication_digest(self.stage_feed))


class LegacyPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.now = datetime(2026, 10, 14, tzinfo=timezone.utc)
        token = issue_license(cls.key, username="Customer", hwid="a" * 64, days=365,
                              issuer="issuer", audience="product", now=cls.now)
        cls.record = parse_signed_csv(f"hwid,token\n{'a' * 64},{token}\n")[0]

    def test_two_column_csv_round_trips_signed_tokens_and_blank_device_rows(self):
        feed = FeedDocument((self.record,), (), disabled_hwids=("b" * 64,))
        csv_text = serialize_legacy_feed(feed)
        rows = list(csv.reader(io.StringIO(csv_text)))
        self.assertEqual(rows[0], ["HWID", "JWT Token"])
        self.assertTrue(all(len(row) == 2 for row in rows))
        parsed = parse_publication_csv(csv_text)
        self.assertEqual(parsed, feed)
        self.assertNotEqual(publication_digest(parsed), publication_digest(FeedDocument((self.record,), ())))

    def test_invalid_and_duplicate_device_rows_are_rejected(self):
        for value in ("HWID,JWT Token\nbad,\n", f"HWID,JWT Token\n{'a'*64},\n{'a'*64},\n",
                      f"HWID,JWT Token\n{'a'*64},,unexpected\n"):
            with self.subTest(value=value), self.assertRaises(LicenseIssueError):
                parse_publication_csv(value)

    def test_revoke_keeps_blank_row_and_remove_omits_it_after_verified_publish(self):
        client = LegacyProtocolClient((self.record,))
        revoked = client.publish_records((), tombstones=(), signing_key=None, issuer="issuer",
                                        audience="product", expected_revision=None,
                                        expected_digest=client.current.digest, disabled_hwids=(self.record.hwid,))
        self.assertEqual(revoked.records, ())
        self.assertEqual(revoked.disabled_hwids, (self.record.hwid,))
        self.assertIsNone(revoked.manifest)
        self.assertIn("verify-stage", client.events)
        removed = client.publish_records((), tombstones=(), signing_key=None, issuer="issuer",
                                        audience="product", expected_revision=revoked.revision,
                                        expected_digest=revoked.digest)
        self.assertEqual(removed.disabled_hwids, ())
        self.assertEqual(serialize_legacy_feed(client.stage_feed), "HWID,JWT Token\n")

    def test_legacy_publish_does_not_confirm_readback_or_stage_mismatch(self):
        class BadReadback(LegacyProtocolClient):
            def _publish_batch(self, **kwargs):
                super()._publish_batch(**kwargs)
                self.current = replace(self.current, digest="wrong")

        class BadStage(LegacyProtocolClient):
            def _read_feed_from_title(self, title):
                return FeedDocument((), ())

        for client in (BadReadback(), BadStage()):
            with self.subTest(client=type(client).__name__), self.assertRaises(LicenseIssueError):
                client.publish_records((self.record,), tombstones=(), signing_key=None,
                                       issuer="issuer", audience="product", expected_revision=None,
                                       expected_digest=client.current.digest)

    def test_legacy_publish_rejects_a_changed_preview(self):
        client = LegacyProtocolClient()
        with self.assertRaises(SheetConflictError):
            client.publish_records((self.record,), tombstones=(), signing_key=None, issuer="issuer",
                                   audience="product", expected_revision=None, expected_digest="stale")
        self.assertNotIn("create-stage", client.events)

    def test_existing_v2_sheet_can_be_converted_to_two_columns(self):
        client = LegacyProtocolClient()
        feed = sign_feed((self.record,), (FeedTombstone("b" * 64, None, self.now),), self.key,
                         revision=7, issuer="issuer", audience="product", generated_at=self.now)
        digest = feed_digest(feed)
        client.current = replace(client.current, records=feed.records, tombstones=feed.tombstones,
                                 manifest_token=feed.manifest_token, manifest=feed.manifest,
                                 digest=digest, revision=RemoteRevision(7, digest, 91, 42, "old"))
        result = client.publish_records((self.record,), tombstones=(), signing_key=None,
                                        issuer="issuer", audience="product", expected_revision=client.current.revision,
                                        expected_digest=digest, disabled_hwids=("b" * 64,))
        self.assertEqual(result.revision.generation, 8)
        self.assertFalse(result.manifest_token)
        self.assertEqual(result.disabled_hwids, ("b" * 64,))
        self.assertEqual(len(next(csv.reader(io.StringIO(serialize_legacy_feed(client.stage_feed))))), 2)

    def test_transport_error_after_commit_is_reconciled_by_readback(self):
        class CommittedButTimedOut(LegacyProtocolClient):
            def _publish_batch(self, **kwargs):
                super()._publish_batch(**kwargs)
                raise LicenseIssueError("Request timed out after commit")
        client = CommittedButTimedOut()
        result = client.publish_records((self.record,), tombstones=(), signing_key=None,
                                        issuer="issuer", audience="product", expected_revision=None,
                                        expected_digest=client.current.digest)
        self.assertEqual(result.records, (self.record,))

    def test_real_sheet_read_and_write_keep_blank_rows_and_only_two_values(self):
        class Capture(GoogleSheetsClient):
            def __init__(self):
                super().__init__(GoogleSheetsConfig("a" * 30, feed_format=LEGACY))
                self.writes = []
            def _request(self, method, url, **kwargs):
                self.writes.append((method, kwargs))
                return {}
            def _read_rows(self, title, cell_range="A:B"):
                return [["HWID", "JWT Token", "", "", ""], [self.record.hwid, self.record.token], ["b" * 64]]
        client = Capture()
        client.record = self.record
        parsed = client._read_feed_from_title("Signed")
        self.assertEqual(parsed.disabled_hwids, ("b" * 64,))
        client._write_feed("Signed", parsed)
        payload = client.writes[-1][1]["json"]
        self.assertIn("!A1:B3", payload["range"])
        self.assertTrue(all(len(row) == 2 for row in payload["values"]))
        requests = sheet_format_requests(42, 100, LEGACY)
        widths = [item["updateDimensionProperties"]["properties"]["pixelSize"]
                  for item in requests if "updateDimensionProperties" in item]
        self.assertEqual(widths, [440, 600])

    def test_empty_one_row_sheet_is_expanded_before_automatic_formatting(self):
        from test_license_admin_google_sheets import BatchCaptureClient
        client = BatchCaptureClient()
        client.config = replace(client.config, feed_format=LEGACY)
        reviewed = replace(LegacyProtocolClient().current, target_row_count=1, target_column_count=2)
        client._publish_batch(expected=reviewed, stage_sheet_id=77, stage_row_count=1,
                              sentinel_sheet_id=92, generation=1, digest="a" * 64, operation_id="op")
        grids = [item["updateSheetProperties"]["properties"].get("gridProperties", {})
                 for item in client.batches[0] if "updateSheetProperties" in item]
        self.assertTrue(any(grid.get("rowCount") == 2 for grid in grids))

    def test_removal_intent_survives_save_reload_and_reopens_publication(self):
        entries = mark_published(mark_revoked(request_revocation((), self.record)), revision=3,
                                 published_at=self.now)
        removed = request_device_removal(entries, self.record)
        self.assertTrue(removed[0].remove_device)
        self.assertIs(removed[0].phase, RevocationPhase.PENDING)
        self.assertIsNone(removed[0].published_revision)
        with workspace_temp_dir() as tmp:
            repo = RevocationRepository(Path(tmp) / "revocations.json")
            repo.save(removed)
            self.assertEqual(repo.load(), removed)

    def test_format_defaults_to_compatibility_and_persists_v2_opt_in(self):
        with workspace_temp_dir() as tmp:
            store = ProjectStore(Path(tmp) / "projects")
            profile = store.create("Example")
            self.assertEqual(profile.feed_format, LEGACY)
            store.save(replace(profile, feed_format="signed-v2"))
            self.assertEqual(store.load(profile.project_id).feed_format, "signed-v2")

    def test_legacy_removal_and_formats_are_in_the_same_atomic_batch(self):
        from test_license_admin_google_sheets import BatchCaptureClient
        client = BatchCaptureClient()
        client.config = replace(client.config, feed_format=LEGACY)
        reviewed = LegacyProtocolClient().current
        client._publish_batch(expected=reviewed, stage_sheet_id=77, stage_row_count=1,
                              sentinel_sheet_id=92, generation=1, digest="a" * 64, operation_id="op")
        self.assertEqual(len(client.batches), 1)
        clear = next(item["updateCells"] for item in client.batches[0]
                     if "updateCells" in item and "range" in item["updateCells"])
        self.assertEqual(clear["range"]["endColumnIndex"], 5)
        self.assertEqual(clear["rows"], [])
        self.assertEqual(client.batches[0][-1], {"deleteSheet": {"sheetId": 77}})
        widths = [item["updateDimensionProperties"]["properties"]["pixelSize"]
                  for item in client.batches[0] if "updateDimensionProperties" in item]
        self.assertEqual(widths, [440, 600])
