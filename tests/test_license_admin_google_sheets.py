from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import unittest

from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError, issue_license
from license_admin.domain import LicenseRecord, parse_signed_csv, records_digest
from license_admin.feed_manifest import FeedDocument, feed_digest, publication_content_digest
from license_admin.google_sheets import (
    GoogleSheetsClient,
    GoogleSheetsConfig,
    RemoteRevision,
    RemoteSnapshot,
    SheetConflictError,
    extract_spreadsheet_id,
)

TEST_ISSUER = "test-license-server"
TEST_AUDIENCE = "test-desktop"


class RecordingSheetsClient(GoogleSheetsClient):
    def __init__(self, existing: list[LicenseRecord]) -> None:
        super().__init__(
            GoogleSheetsConfig(
                spreadsheet_id="a" * 30,
                worksheet="Signed",
                credentials_path=Path("unused.json"),
            )
        )
        self.existing = existing
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def read_records(self) -> list[LicenseRecord]:
        return self.existing

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append((method, url, kwargs))
        if method == "GET":
            return {
                "sheets": [
                    {
                        "properties": {
                            "sheetId": 42,
                            "title": "Signed",
                            "gridProperties": {"rowCount": 1_000},
                        }
                    }
                ]
            }
        return {}


class ProtocolSheetsClient(GoogleSheetsClient):
    def __init__(self, existing: list[LicenseRecord]) -> None:
        super().__init__(
            GoogleSheetsConfig(
                spreadsheet_id="a" * 30,
                worksheet="Signed",
                credentials_path=Path("unused.json"),
            )
        )
        digest = records_digest(existing)
        self.current = RemoteSnapshot(
            records=tuple(existing),
            digest=digest,
            revision=None,
            target_sheet_id=42,
            target_row_count=1_000,
        )
        self.stage_records: tuple[LicenseRecord, ...] = ()
        self.stage_feed: FeedDocument | None = None
        self.stage_identity: tuple[int, str] | None = None
        self.events: list[str] = []

    def read_snapshot(self) -> RemoteSnapshot:
        return self.current

    def _sheet_properties(self) -> dict[str, tuple[int, int, int, bool]]:
        properties = {"Signed": (42, 1_000, 26, False)}
        if self.current.revision is not None:
            properties[self._sentinel_title()] = (
                self.current.revision.sentinel_sheet_id,
                2,
                5,
                True,
            )
        if self.stage_identity is not None:
            stage_id, stage_title = self.stage_identity
            properties[stage_title] = (
                stage_id,
                len(self.stage_records) + 1,
                2,
                True,
            )
        return properties

    def _create_stage(self, sheet_id: int, title: str, row_count: int) -> None:
        self.events.append("create-stage")
        self.stage_identity = (sheet_id, title)

    def _write_feed(
        self,
        title: str,
        feed: FeedDocument,
    ) -> None:
        self.events.append("write-stage")
        self.stage_feed = feed
        self.stage_records = feed.records

    def _read_feed_from_title(self, title: str) -> FeedDocument:
        self.events.append("verify-stage")
        if self.stage_feed is None:
            raise AssertionError("stage feed was not written")
        return self.stage_feed

    def _publish_batch(
        self,
        *,
        expected: RemoteSnapshot,
        stage_sheet_id: int,
        stage_row_count: int,
        sentinel_sheet_id: int,
        generation: int,
        digest: str,
        operation_id: str,
    ) -> None:
        self.events.append("atomic-publish")
        self.stage_identity = None
        if self.stage_feed is None:
            raise AssertionError("stage feed was not written")
        self.current = RemoteSnapshot(
            records=self.stage_records,
            digest=digest,
            revision=RemoteRevision(
                generation=generation,
                digest=digest,
                sentinel_sheet_id=sentinel_sheet_id,
                target_sheet_id=expected.target_sheet_id,
                operation_id=operation_id,
            ),
            target_sheet_id=expected.target_sheet_id,
            target_row_count=expected.target_row_count,
            target_column_count=5,
            tombstones=self.stage_feed.tombstones,
            manifest_token=self.stage_feed.manifest_token,
            content_digest=publication_content_digest(
                self.stage_feed.records,
                self.stage_feed.tombstones,
            ),
        )

    def _delete_sheet(self, sheet_id: int) -> None:
        self.events.append("cleanup-stage")
        if self.stage_identity is not None and self.stage_identity[0] == sheet_id:
            self.stage_identity = None


class BatchCaptureClient(GoogleSheetsClient):
    def __init__(self) -> None:
        super().__init__(
            GoogleSheetsConfig(
                spreadsheet_id="a" * 30,
                worksheet="Signed",
                credentials_path=Path("unused.json"),
            )
        )
        self.batches: list[list[dict[str, Any]]] = []

    def _batch_update(self, requests_payload: list[dict[str, Any]]) -> Any:
        self.batches.append(requests_payload)
        return {}


class StageMismatchClient(ProtocolSheetsClient):
    def _read_feed_from_title(self, title: str) -> FeedDocument:
        self.events.append("verify-stage")
        return FeedDocument((), (), "invalid")


class ReadbackMismatchClient(ProtocolSheetsClient):
    def _publish_batch(
        self,
        *,
        expected: RemoteSnapshot,
        stage_sheet_id: int,
        stage_row_count: int,
        sentinel_sheet_id: int,
        generation: int,
        digest: str,
        operation_id: str,
    ) -> None:
        super()._publish_batch(
            expected=expected,
            stage_sheet_id=stage_sheet_id,
            stage_row_count=stage_row_count,
            sentinel_sheet_id=sentinel_sheet_id,
            generation=generation,
            digest=digest,
            operation_id=operation_id,
        )
        self.current = RemoteSnapshot(
            records=(),
            digest=feed_digest(self.stage_feed) if self.stage_feed is not None else records_digest(()),
            revision=self.current.revision,
            target_sheet_id=expected.target_sheet_id,
            target_row_count=expected.target_row_count,
            target_column_count=5,
            tombstones=self.current.tombstones,
            manifest_token=self.current.manifest_token,
            content_digest=publication_content_digest((), self.current.tombstones),
        )


class CreateTimeoutClient(ProtocolSheetsClient):
    def _create_stage(self, sheet_id: int, title: str, row_count: int) -> None:
        super()._create_stage(sheet_id, title, row_count)
        raise LicenseIssueError("create response was lost")


class LicenseAdminGoogleSheetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_key = rsa.generate_private_key(
            public_exponent=65_537,
            key_size=2_048,
        )

    def _record(self, character: str) -> LicenseRecord:
        hwid = character * 64
        token = issue_license(
            self.private_key,
            username=f"User {character}",
            hwid=hwid,
            days=365,
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            now=datetime(2026, 9, 28, tzinfo=timezone.utc),
        )
        return parse_signed_csv(f"{hwid},{token}\n")[0]

    def _publish(
        self,
        client: GoogleSheetsClient,
        records: list[LicenseRecord],
        *,
        expected_revision: RemoteRevision | None,
        expected_digest: str,
    ) -> RemoteSnapshot:
        return client.publish_records(
            records,
            tombstones=(),
            signing_key=self.private_key,
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            expected_revision=expected_revision,
            expected_digest=expected_digest,
        )

    def test_extracts_id_from_sheet_urls(self) -> None:
        sheet_id = "abcDEF_12345678901234567890"
        self.assertEqual(
            extract_spreadsheet_id(
                f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid=0"
            ),
            sheet_id,
        )
        self.assertEqual(extract_spreadsheet_id(sheet_id), sheet_id)
        with self.assertRaises(LicenseIssueError):
            extract_spreadsheet_id("not a sheet")

    def test_publish_stages_verifies_and_atomically_swaps_before_readback(self) -> None:
        existing = [self._record("a"), self._record("b"), self._record("c")]
        client = ProtocolSheetsClient(existing)
        desired = [existing[0]]

        result = self._publish(
            client,
            desired,
            expected_revision=None,
            expected_digest=records_digest(existing),
        )

        self.assertEqual(
            client.events,
            ["create-stage", "write-stage", "verify-stage", "atomic-publish"],
        )
        self.assertEqual(result.records, tuple(desired))
        self.assertIsNotNone(client.stage_feed)
        assert client.stage_feed is not None
        self.assertEqual(result.digest, feed_digest(client.stage_feed))
        self.assertEqual(result.revision.generation if result.revision else None, 1)

    def test_stale_remote_snapshot_is_rejected_before_staging(self) -> None:
        existing = [self._record("a")]
        changed = [self._record("b")]
        client = ProtocolSheetsClient(changed)

        with self.assertRaises(SheetConflictError):
            self._publish(
                client,
                existing,
                expected_revision=None,
                expected_digest=records_digest(existing),
            )

        self.assertEqual(client.events, [])

    def test_existing_remote_revision_advances_exactly_once(self) -> None:
        existing = [self._record("a")]
        client = ProtocolSheetsClient(existing)
        digest = records_digest(existing)
        revision = RemoteRevision(4, digest, 91, 42, "previous")
        client.current = RemoteSnapshot(tuple(existing), digest, revision, 42, 1_000)

        result = self._publish(
            client,
            [self._record("b")],
            expected_revision=revision,
            expected_digest=digest,
        )

        self.assertIsNotNone(result.revision)
        self.assertEqual(result.revision.generation if result.revision else None, 5)
        self.assertNotEqual(
            result.revision.sentinel_sheet_id if result.revision else None,
            revision.sentinel_sheet_id,
        )

    def test_stage_verification_failure_never_reaches_canonical_sheet(self) -> None:
        existing = [self._record("a")]
        client = StageMismatchClient(existing)

        with self.assertRaisesRegex(LicenseIssueError, "staging verification"):
            self._publish(
                client,
                [self._record("b")],
                expected_revision=None,
                expected_digest=records_digest(existing),
            )

        self.assertEqual(
            client.events,
            ["create-stage", "write-stage", "verify-stage", "cleanup-stage"],
        )
        self.assertEqual(client.current.records, tuple(existing))

    def test_readback_mismatch_is_never_reported_as_success(self) -> None:
        existing = [self._record("a")]
        client = ReadbackMismatchClient(existing)

        with self.assertRaisesRegex(LicenseIssueError, "read-back verification"):
            self._publish(
                client,
                [self._record("b")],
                expected_revision=None,
                expected_digest=records_digest(existing),
            )

    def test_ambiguous_stage_creation_cleans_exact_owned_sheet(self) -> None:
        existing = [self._record("a")]
        client = CreateTimeoutClient(existing)

        with self.assertRaisesRegex(LicenseIssueError, "response was lost"):
            self._publish(
                client,
                [self._record("b")],
                expected_revision=None,
                expected_digest=records_digest(existing),
            )

        self.assertEqual(client.events, ["create-stage", "cleanup-stage"])
        self.assertIsNone(client.stage_identity)

    def test_reconcile_requires_exact_sentinel_and_target_identity(self) -> None:
        digest = "a" * 64
        snapshot = RemoteSnapshot(
            records=(),
            digest=digest,
            revision=RemoteRevision(2, digest, 999, 42, "operation"),
            target_sheet_id=42,
            target_row_count=1_000,
        )

        self.assertFalse(
            GoogleSheetsClient._is_verified_publish(
                snapshot,
                operation_id="operation",
                generation=2,
                sentinel_sheet_id=91,
                target_sheet_id=42,
                digest=digest,
            )
        )

    def test_revision_comparison_includes_operation_id(self) -> None:
        digest = "a" * 64
        expected = RemoteRevision(2, digest, 91, 42, "expected-operation")
        changed = RemoteRevision(2, digest, 91, 42, "different-operation")

        self.assertFalse(GoogleSheetsClient._same_revision(changed, expected))

    def test_atomic_publish_expands_narrow_target_to_two_columns(self) -> None:
        client = BatchCaptureClient()
        expected = RemoteSnapshot(
            records=(),
            digest="a" * 64,
            revision=None,
            target_sheet_id=42,
            target_row_count=100,
            target_column_count=1,
        )

        client._publish_batch(
            expected=expected,
            stage_sheet_id=77,
            stage_row_count=5,
            sentinel_sheet_id=92,
            generation=1,
            digest="b" * 64,
            operation_id="next",
        )

        expand = next(
            request["updateSheetProperties"]
            for request in client.batches[0]
            if "updateSheetProperties" in request
        )
        self.assertEqual(
            expand["properties"]["gridProperties"],
            {"rowCount": 100, "columnCount": 5},
        )
        self.assertIn("gridProperties.columnCount", expand["fields"])

    def test_final_publish_is_one_atomic_guarded_batch(self) -> None:
        client = BatchCaptureClient()
        digest = "a" * 64
        revision = RemoteRevision(
            generation=7,
            digest=digest,
            sentinel_sheet_id=91,
            target_sheet_id=42,
            operation_id="previous",
        )
        expected = RemoteSnapshot((), digest, revision, 42, 1_000)

        client._publish_batch(
            expected=expected,
            stage_sheet_id=77,
            stage_row_count=5,
            sentinel_sheet_id=92,
            generation=8,
            digest="b" * 64,
            operation_id="next",
        )

        self.assertEqual(len(client.batches), 1)
        requests_payload = client.batches[0]
        self.assertEqual(requests_payload[0], {"deleteSheet": {"sheetId": 91}})
        self.assertEqual(
            requests_payload[1]["addSheet"]["properties"]["sheetId"],
            92,
        )
        request_kinds = [next(iter(item)) for item in requests_payload]
        self.assertIn("updateCells", request_kinds)
        self.assertIn("copyPaste", request_kinds)
        self.assertEqual(requests_payload[-1], {"deleteSheet": {"sheetId": 77}})
        copy_request = next(item["copyPaste"] for item in requests_payload if "copyPaste" in item)
        self.assertEqual(copy_request["destination"]["sheetId"], 42)

    def test_format_freezes_header_formats_text_and_adds_filter(self) -> None:
        client = RecordingSheetsClient([])

        client.format_worksheet()

        self.assertEqual([call[0] for call in client.calls], ["GET", "POST"])
        requests_payload = client.calls[1][2]["json"]["requests"]
        request_kinds = {next(iter(item)) for item in requests_payload}
        self.assertIn("updateSheetProperties", request_kinds)
        self.assertIn("repeatCell", request_kinds)
        self.assertIn("updateDimensionProperties", request_kinds)
        self.assertIn("setBasicFilter", request_kinds)


if __name__ == "__main__":
    unittest.main()
