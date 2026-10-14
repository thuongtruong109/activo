"""Compatibility CSV for clients that only read HWID and JWT Token."""

import csv
import hashlib
import io

from issue_license import LicenseIssueError, normalize_hwid
from license_admin.domain import parse_signed_csv
from license_admin.feed_manifest import FeedDocument, parse_feed_csv, serialize_feed_csv
from license_admin.limits import MAX_LICENSE_FEED_BYTES, MAX_LICENSE_FEED_ROWS


LEGACY = "legacy"
SIGNED_V2 = "signed-v2"


def validate_feed_format(value: str) -> str:
    if value not in {LEGACY, SIGNED_V2}:
        raise LicenseIssueError("Unsupported publication format.")
    return value


def serialize_legacy_feed(feed: FeedDocument) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("HWID", "JWT Token"))
    values = {record.hwid: record.token for record in feed.records}
    for hwid in feed.disabled_hwids:
        if hwid in values:
            raise LicenseIssueError("An HWID cannot have both a token and a disabled row.")
        values[normalize_hwid(hwid)] = ""
    for hwid, token in sorted(values.items()):
        writer.writerow((hwid, token))
    return output.getvalue()


def parse_publication_csv(value: str) -> FeedDocument:
    if len(value.encode("utf-8")) > MAX_LICENSE_FEED_BYTES:
        raise LicenseIssueError("The publication CSV is too large.")
    try:
        rows = list(csv.reader(io.StringIO(value.lstrip("\ufeff")), strict=True))
    except csv.Error as exc:
        raise LicenseIssueError("The publication CSV is invalid.") from exc
    if len(rows) > MAX_LICENSE_FEED_ROWS:
        raise LicenseIssueError("The publication CSV has too many rows.")
    if rows and rows[0] and rows[0][0].strip() == "entry_type":
        return parse_feed_csv(value)
    active_rows: list[list[str]] = []
    disabled: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not row or not any(field.strip() for field in row):
            continue
        if row[0].strip().casefold() == "hwid":
            if len(row) != 2 or row[1].strip().casefold() not in {"token", "jwt token", "jwt_token", "license_token"}:
                raise LicenseIssueError("Unsupported two-column header.")
            continue
        if len(row) not in {1, 2}:
            raise LicenseIssueError("A compatibility CSV must contain only HWID and JWT Token.")
        hwid = normalize_hwid(row[0])
        if hwid in seen:
            raise LicenseIssueError("The publication CSV contains duplicate HWIDs.")
        seen.add(hwid)
        token = row[1].strip() if len(row) == 2 else ""
        if token:
            active_rows.append([hwid, token])
        else:
            disabled.append(hwid)
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(active_rows)
    return FeedDocument(tuple(parse_signed_csv(output.getvalue())), (), disabled_hwids=tuple(sorted(disabled)))


def publication_csv(feed: FeedDocument) -> str:
    return serialize_feed_csv(feed) if feed.manifest_token else serialize_legacy_feed(feed)


def publication_digest(feed: FeedDocument) -> str:
    return hashlib.sha256(publication_csv(feed).encode("utf-8")).hexdigest()
