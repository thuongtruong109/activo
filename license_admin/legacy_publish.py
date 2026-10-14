"""Staged two-column publication with conflict guards and exact read-back checks."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from issue_license import LicenseIssueError
from license_admin.domain import LicenseRecord
from license_admin.feed_format import publication_digest
from license_admin.feed_manifest import FeedDocument

if TYPE_CHECKING:
    from license_admin.google_sheets import GoogleSheetsClient, RemoteRevision, RemoteSnapshot


def publish_legacy(
    client: GoogleSheetsClient, records: tuple[LicenseRecord, ...], disabled_hwids: tuple[str, ...],
    *, expected_revision: RemoteRevision | None, expected_digest: str,
) -> RemoteSnapshot:
    reviewed = client.read_snapshot()
    client._assert_expected_snapshot(reviewed, expected_revision, expected_digest)
    feed = FeedDocument(records, (), disabled_hwids=disabled_hwids)
    digest = publication_digest(feed)
    generation = expected_revision.generation + 1 if expected_revision else 1
    properties = client._sheet_properties()
    used_ids = {item[0] for item in properties.values()}
    stage_id = client._new_sheet_id(used_ids)
    sentinel_id = client._new_sheet_id(used_ids)
    operation_id = uuid4().hex
    stage_title = f"__activo_stage_{operation_id}"
    row_count = len(records) + len(disabled_hwids) + 1
    cleanup = True

    def confirmed(snapshot: RemoteSnapshot) -> bool:
        revision = snapshot.revision
        return bool(
            revision and revision.generation == generation and revision.digest == digest
            and revision.operation_id == operation_id and revision.sentinel_sheet_id == sentinel_id
            and revision.target_sheet_id == reviewed.target_sheet_id and snapshot.digest == digest
        )

    try:
        client._create_stage(stage_id, stage_title, row_count)
        client._write_feed(stage_title, feed)
        if publication_digest(client._read_feed_from_title(stage_title)) != digest:
            raise LicenseIssueError("Staging verification failed; published data was untouched.")
        current = client.read_snapshot()
        client._assert_expected_snapshot(current, expected_revision, expected_digest)
        try:
            client._publish_batch(
                expected=current, stage_sheet_id=stage_id, stage_row_count=row_count,
                sentinel_sheet_id=sentinel_id, generation=generation, digest=digest,
                operation_id=operation_id,
            )
            cleanup = False
        except LicenseIssueError:
            # A transport error can arrive after Google committed the batch.
            reconciled = client.read_snapshot()
            if confirmed(reconciled):
                cleanup = False
                return reconciled
            raise
        verified = client.read_snapshot()
        if not confirmed(verified):
            raise LicenseIssueError("Sheet read-back verification failed; sync was not confirmed.")
        return verified
    finally:
        if cleanup:
            client._cleanup_stage(stage_id, stage_title)
